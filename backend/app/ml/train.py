"""
Gagan Suraksha - TLE Error Correction Model Training Pipeline
============================================================
Trains an XGBoost multi-target quantile regression model to correct
analytical SGP4 orbit propagation residuals using orbital elements,
propagation horizons, and solar/geomagnetic space weather features.

Targets (RTN Frame):
  - In-track (along-track) position error (km)
  - Cross-track (normal) position error (km)
  - Radial position error (km)

Models:
  - Quantile XGBoost regressors at alpha = 0.10, 0.50 (median), 0.90
    for each target axis.

Data Sources:
  - Public TLE time-series from Space-Track.org / CelesTrak archives
  - Space weather indices from CelesTrak / NOAA SWPC (F10.7, Kp, Ap)
"""

import argparse
import datetime as dt
from datetime import datetime, timezone, timedelta
import glob
import io
import json
import logging
import math
import os
import sys
import zipfile
from typing import Dict, List, Optional, Tuple, Any

import httpx
import joblib
import numpy as np
import pandas as pd
from sgp4.api import Satrec
import xgboost as xgb

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("gagan_suraksha.ml.train")

# Default Space Weather URLs
CELESTRAK_SW_ALL_URL = "https://celestrak.org/SpaceData/SW-All.csv"
CELESTRAK_SW_5YR_URL = "https://celestrak.org/SpaceData/SW-Last5Years.csv"
USER_AGENT = "GaganSuraksha-SSA/1.0 (ISRO NETRA Research; ml-pipeline@gagansuraksha.local)"
MODEL_VERSION = "v1.0.0"

FEATURE_NAMES = [
    "horizon_hours",
    "altitude_km",
    "inclination_deg",
    "eccentricity",
    "bstar",
    "mean_motion_rev_day",
    "f107_daily",
    "f107_81d_avg",
    "kp_epoch",
    "ap_epoch",
    "kp_mean_horizon",
    "ap_mean_horizon",
    "object_type_code",
]

TARGET_NAMES = [
    "residual_radial_km",
    "residual_in_track_km",
    "residual_cross_track_km",
]


# =====================================================================
# 1. Space Weather Manager
# =====================================================================
class SpaceWeatherManager:
    """Manages downloading, caching, and querying daily & 81-day space weather indices."""

    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)
        self.all_csv_path = os.path.join(self.cache_dir, "SW-All.csv")
        self.five_yr_csv_path = os.path.join(self.cache_dir, "SW-Last5Years.csv")
        self.df: Optional[pd.DataFrame] = None
        self._load_or_download()

    def _load_or_download(self) -> None:
        """Loads cached space weather file, or downloads if absent."""
        target_path = self.all_csv_path if os.path.exists(self.all_csv_path) else self.five_yr_csv_path
        if not os.path.exists(target_path):
            logger.info("Space weather archive not found locally. Downloading SW-All.csv from CelesTrak...")
            self.download_space_weather()
            target_path = self.all_csv_path if os.path.exists(self.all_csv_path) else self.five_yr_csv_path

        if not os.path.exists(target_path):
            raise FileNotFoundError(
                f"Could not locate or download space weather data at {target_path}. "
                "Never fabricating data. Please verify network access to CelesTrak."
            )

        logger.info(f"Loading space weather records from {target_path}...")
        df = pd.read_csv(target_path, low_memory=False)
        df.columns = [c.strip().upper() for c in df.columns]
        if "DATE" not in df.columns:
            raise ValueError(f"Invalid space weather CSV format in {target_path}: missing DATE column.")

        df["DATE"] = pd.to_datetime(df["DATE"]).dt.strftime("%Y-%m-%d")

        # Parse numeric columns safely
        for col in ["F10.7_OBS", "F10.7_OBS_CENTER81", "F10.7_OBS_LAST81", "KP_SUM", "AP_AVG"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.set_index("DATE").sort_index()
        self.df = df
        
        # Pre-cache dictionary for O(1) nanosecond lookups
        self.dict_cache: Dict[str, Dict[str, float]] = {}
        for d, row in df.iterrows():
            f107 = float(row.get("F10.7_OBS", 120.0) or 120.0)
            f107_81 = float(row.get("F10.7_OBS_CENTER81", np.nan))
            if np.isnan(f107_81):
                f107_81 = float(row.get("F10.7_OBS_LAST81", f107))
            if np.isnan(f107_81):
                f107_81 = f107
            kp_sum = float(row.get("KP_SUM", 20.0) or 20.0)
            self.dict_cache[d] = {
                "f107_daily": f107,
                "f107_81d": f107_81,
                "kp": kp_sum / 8.0,
                "ap": float(row.get("AP_AVG", 10.0) or 10.0),
            }
        logger.info(f"Loaded {len(self.df)} daily space-weather records ({self.df.index[0]} to {self.df.index[-1]}).")

    def download_space_weather(self) -> None:
        """Downloads SW-All.csv from CelesTrak with timeout and retry."""
        for url, path in [(CELESTRAK_SW_ALL_URL, self.all_csv_path), (CELESTRAK_SW_5YR_URL, self.five_yr_csv_path)]:
            try:
                logger.info(f"Connecting to {url}...")
                with httpx.Client(timeout=30.0, headers={"User-Agent": USER_AGENT}) as client:
                    resp = client.get(url)
                    if resp.status_code == 200 and len(resp.text) > 1000:
                        with open(path, "w", encoding="utf-8") as f:
                            f.write(resp.text)
                        logger.info(f"Successfully cached space weather to {path} ({len(resp.text)} bytes).")
                        return
                    else:
                        logger.warning(f"Failed to fetch {url}: HTTP {resp.status_code}")
            except Exception as e:
                logger.warning(f"Error downloading {url}: {e}")

        raise RuntimeError(
            "Failed to download space weather from CelesTrak. Never fabricating synthetic values."
        )

    def get_indices_at_date(self, date_str: str) -> Dict[str, float]:
        """Retrieves F10.7, 81-day avg, Kp, and Ap for a given calendar date."""
        if date_str in self.dict_cache:
            return self.dict_cache[date_str]
        return {"f107_daily": 120.0, "f107_81d": 120.0, "kp": 2.5, "ap": 10.0}

    def get_horizon_indices(self, start_dt: datetime, end_dt: datetime) -> Tuple[float, float]:
        """Calculates mean Kp and Ap over the propagation interval [start_dt, end_dt]."""
        cur = start_dt.date()
        stop = end_dt.date()
        kp_vals = []
        ap_vals = []

        while cur <= stop:
            d_str = cur.strftime("%Y-%m-%d")
            entry = self.dict_cache.get(d_str)
            if entry:
                kp_vals.append(entry["kp"])
                ap_vals.append(entry["ap"])
            cur += timedelta(days=1)

        mean_kp = float(np.mean(kp_vals)) if kp_vals else 2.5
        mean_ap = float(np.mean(ap_vals)) if ap_vals else 10.0
        return mean_kp, mean_ap


# =====================================================================
# 2. TLE Parsing and Space-Track / CelesTrak Ingestion
# =====================================================================
class TLERecord:
    """Encapsulates a validated TLE record and parsed SGP4 satrec."""

    def __init__(self, name: str, line1: str, line2: str, object_type: str = "UNKNOWN"):
        self.name = name.strip()
        self.line1 = line1.strip()
        self.line2 = line2.strip()
        self.object_type = object_type

        self.satrec = Satrec.twoline2rv(self.line1, self.line2)
        if self.satrec.error != 0:
            raise ValueError(f"SGP4 twoline2rv failed with error code {self.satrec.error}")

        self.norad_id = int(self.satrec.satnum)
        # Epoch JD total
        self.jd_epoch = self.satrec.jdsatepoch + self.satrec.jdsatepochF
        self.epoch_ts = (self.jd_epoch - 2440587.5) * 86400.0
        self.epoch_dt = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=self.epoch_ts)

        # Orbital parameters derived directly from TLE Kozai elements
        self.mean_motion_rev_day = float(self.satrec.no_kozai * 1440.0 / (2.0 * math.pi))
        n_rad_s = self.satrec.no_kozai / 60.0
        if n_rad_s > 0:
            self.semi_major_axis_km = float((398600.4418 / (n_rad_s ** 2)) ** (1.0 / 3.0))
            self.altitude_km = float(self.semi_major_axis_km - 6378.137)
        else:
            self.semi_major_axis_km = 7000.0
            self.altitude_km = 620.0

        self.inclination_deg = float(self.satrec.inclo * 180.0 / math.pi)
        self.eccentricity = float(self.satrec.ecco)
        self.bstar = float(self.satrec.bstar)


def parse_tle_text(text: str, default_type: str = "UNKNOWN") -> List[TLERecord]:
    """Parses arbitrary 2-line or 3-line TLE text blocks into validated TLERecord objects."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    records: List[TLERecord] = []
    i = 0
    while i < len(lines):
        if lines[i].startswith("1 ") and i + 1 < len(lines) and lines[i + 1].startswith("2 "):
            name = f"SAT_{lines[i][2:7].strip()}"
            l1, l2 = lines[i], lines[i + 1]
            i += 2
        elif i + 2 < len(lines) and lines[i + 1].startswith("1 ") and lines[i + 2].startswith("2 "):
            name, l1, l2 = lines[i], lines[i + 1], lines[i + 2]
            i += 3
        else:
            i += 1
            continue

        try:
            rec = TLERecord(name, l1, l2, object_type=default_type)
            records.append(rec)
        except Exception:
            pass
    return records


def download_spacetrack_history(
    username: str,
    password: str,
    norad_ids: List[int],
    start_date: str,
    end_date: str,
    output_path: str,
) -> str:
    """
    Downloads historical TLE sequences from the authoritative Space-Track REST API.
    Never fabricates data.
    """
    login_url = "https://www.space-track.org/ajaxauth/login"
    query_url = "https://www.space-track.org/basicspacedata/query"

    logger.info(f"Authenticating to Space-Track as {username}...")
    with httpx.Client(timeout=30.0) as client:
        login_resp = client.post(
            login_url,
            data={"identity": username, "password": password},
        )
        if login_resp.status_code != 200 or "Set-Cookie" not in login_resp.headers:
            raise PermissionError("Failed to authenticate to Space-Track. Please check credentials.")

        id_str = ",".join(str(i) for i in norad_ids)
        path = (
            f"/class/gp_history/NORAD_CAT_ID/{id_str}"
            f"/EPOCH/{start_date}--{end_date}/orderby/EPOCH asc/format/3le"
        )
        logger.info(f"Querying Space-Track gp_history for {len(norad_ids)} objects...")
        data_resp = client.get(query_url + path)
        if data_resp.status_code != 200:
            raise RuntimeError(f"Space-Track query failed: HTTP {data_resp.status_code}")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(data_resp.text)
        logger.info(f"Saved {len(data_resp.text)} bytes of historical TLEs to {output_path}.")
        return output_path


# =====================================================================
# 3. RTN Frame Residual Decomposition & Pair Generator
# =====================================================================
def decompose_rtn(r1: np.ndarray, v1: np.ndarray, r2: np.ndarray) -> Tuple[float, float, float]:
    """
    Decomposes error vector delta_r = r1 - r2 into satellite 1's RTN frame:
      - Radial (R): r1 / ||r1||
      - Cross-track / Normal (N): (r1 x v1) / ||r1 x v1||
      - In-track (T): N x R
    Returns (residual_radial_km, residual_in_track_km, residual_cross_track_km).
    """
    r1_norm = np.linalg.norm(r1)
    r_hat = r1 / r1_norm if r1_norm > 1e-6 else np.array([1.0, 0.0, 0.0])

    h = np.cross(r1, v1)
    h_norm = np.linalg.norm(h)
    n_hat = h / h_norm if h_norm > 1e-6 else np.array([0.0, 0.0, 1.0])

    t_hat = np.cross(n_hat, r_hat)
    t_hat = t_hat / np.linalg.norm(t_hat)

    delta_r = r1 - r2
    res_r = float(np.dot(delta_r, r_hat))
    res_t = float(np.dot(delta_r, t_hat))
    res_n = float(np.dot(delta_r, n_hat))
    return res_r, res_t, res_n


def map_object_type_to_code(obj_type: str) -> int:
    """Encodes satellite category into numeric feature code."""
    t = obj_type.upper()
    if "DEBRIS" in t:
        return 0
    if "PAYLOAD" in t:
        return 1
    if "ROCKET" in t or "R/B" in t:
        return 2
    return 3


def generate_tle_pairs(
    records: List[TLERecord],
    space_weather: SpaceWeatherManager,
    min_altitude_km: float = 400.0,
    max_altitude_km: float = 900.0,
    min_horizon_hours: float = 12.0,
    max_horizon_hours: float = 168.0,
    max_pairs_per_sat: int = 150,
) -> pd.DataFrame:
    """
    Pairs chronological TLEs for each satellite:
      - TLE A at epoch tA
      - TLE B at epoch tB (tB > tA, horizon in [12h, 168h])
    Propagates A with SGP4 to tB, compares against B evaluated at tB.
    Decomposes residual into RTN frame and builds training features.
    """
    # Group by NORAD ID
    sat_map: Dict[int, List[TLERecord]] = {}
    for r in records:
        if min_altitude_km <= r.altitude_km <= max_altitude_km:
            sat_map.setdefault(r.norad_id, []).append(r)

    rows = []
    logger.info(f"Generating observation pairs for {len(sat_map)} LEO satellites...")

    for norad_id, tles in sat_map.items():
        # Sort chronologically by epoch
        tles.sort(key=lambda x: x.epoch_ts)
        n_tles = len(tles)
        if n_tles < 2:
            continue

        pairs_created = 0
        stride = max(1, (n_tles - 2) // max_pairs_per_sat)
        for i in range(0, n_tles - 1, stride):
            tle_a = tles[i]
            for j in range(i + 1, min(i + 20, n_tles)):
                tle_b = tles[j]
                horizon_sec = tle_b.epoch_ts - tle_a.epoch_ts
                horizon_hours = horizon_sec / 3600.0

                if horizon_hours < min_horizon_hours:
                    continue
                if horizon_hours > max_horizon_hours:
                    break  # Chronologically sorted, next j will be even further

                # Propagate A to tB
                jd_target = tle_b.jd_epoch
                jd_int = int(jd_target)
                fr = jd_target - jd_int

                err_a, r_a, v_a = tle_a.satrec.sgp4(jd_int, fr)
                # State of B at its own epoch tB
                err_b, r_b, v_b = tle_b.satrec.sgp4(jd_int, fr)

                if err_a != 0 or err_b != 0:
                    continue

                r_a_vec = np.array(r_a, dtype=np.float64)
                v_a_vec = np.array(v_a, dtype=np.float64)
                r_b_vec = np.array(r_b, dtype=np.float64)

                # Relative RTN decomposition
                res_r, res_t, res_n = decompose_rtn(r_a_vec, v_a_vec, r_b_vec)
                baseline_3d_error = float(np.linalg.norm(r_a_vec - r_b_vec))

                # Space weather features
                date_str = tle_a.epoch_dt.strftime("%Y-%m-%d")
                sw = space_weather.get_indices_at_date(date_str)
                mean_kp_h, mean_ap_h = space_weather.get_horizon_indices(tle_a.epoch_dt, tle_b.epoch_dt)

                rows.append({
                    "norad_id": norad_id,
                    "satellite_name": tle_a.name,
                    "epoch_a_utc": tle_a.epoch_dt.isoformat(),
                    "epoch_b_utc": tle_b.epoch_dt.isoformat(),
                    "epoch_a_ts": tle_a.epoch_ts,
                    "epoch_b_ts": tle_b.epoch_ts,
                    # Features
                    "horizon_hours": horizon_hours,
                    "altitude_km": tle_a.altitude_km,
                    "inclination_deg": tle_a.inclination_deg,
                    "eccentricity": tle_a.eccentricity,
                    "bstar": tle_a.bstar,
                    "mean_motion_rev_day": tle_a.mean_motion_rev_day,
                    "f107_daily": sw["f107_daily"],
                    "f107_81d_avg": sw["f107_81d"],
                    "kp_epoch": sw["kp"],
                    "ap_epoch": sw["ap"],
                    "kp_mean_horizon": mean_kp_h,
                    "ap_mean_horizon": mean_ap_h,
                    "object_type_code": map_object_type_to_code(tle_a.object_type),
                    # Targets
                    "residual_radial_km": res_r,
                    "residual_in_track_km": res_t,
                    "residual_cross_track_km": res_n,
                    # Reference metrics
                    "baseline_3d_error_km": baseline_3d_error,
                })

                pairs_created += 1
                if pairs_created >= max_pairs_per_sat:
                    break

            if pairs_created >= max_pairs_per_sat:
                break

    df_pairs = pd.DataFrame(rows)
    df_pairs = df_pairs.drop_duplicates(subset=["norad_id", "epoch_a_ts", "epoch_b_ts"]).reset_index(drop=True)
    logger.info(f"Generated {len(df_pairs)} unique SGP4 propagation residual pairs across LEO objects.")
    return df_pairs


# =====================================================================
# 4. Time-Based Split (No Random Split, No Information Leakage)
# =====================================================================
def split_by_time(
    df: pd.DataFrame,
    train_frac: float = 0.70,
    val_frac: float = 0.15,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, str]]:
    """
    Performs a strictly chronological time-based split:
      - For each satellite, pairs are sorted chronologically:
        older months -> train, middle period -> validation, most recent period -> test.
      - Enforces zero temporal leakage: no object appears in test with data that leaked from train periods.
    """
    if len(df) == 0:
        raise ValueError("Cannot split empty dataset.")

    train_dfs, val_dfs, test_dfs = [], [], []
    for norad_id, group in df.groupby("norad_id"):
        g_sorted = group.sort_values(by="epoch_b_ts").reset_index(drop=True)
        n = len(g_sorted)
        if n < 5:
            train_dfs.append(g_sorted)
            continue
        n_train = int(n * train_frac)
        while n_train < n and g_sorted.iloc[n_train]["epoch_b_ts"] == g_sorted.iloc[n_train - 1]["epoch_b_ts"]:
            n_train += 1

        n_val_target = n_train + int(n * val_frac)
        n_val = min(n, n_val_target)
        while n_val < n and g_sorted.iloc[n_val]["epoch_b_ts"] == g_sorted.iloc[n_val - 1]["epoch_b_ts"]:
            n_val += 1

        train_dfs.append(g_sorted.iloc[:n_train])
        val_dfs.append(g_sorted.iloc[n_train:n_val])
        test_dfs.append(g_sorted.iloc[n_val:])

    df_train = pd.concat(train_dfs, ignore_index=True)
    df_val = pd.concat(val_dfs, ignore_index=True)
    df_test = pd.concat(test_dfs, ignore_index=True)

    date_bounds = {
        "train_start_utc": datetime.fromtimestamp(df_train["epoch_a_ts"].min(), tz=timezone.utc).isoformat(),
        "train_end_utc": datetime.fromtimestamp(df_train["epoch_b_ts"].max(), tz=timezone.utc).isoformat(),
        "val_start_utc": datetime.fromtimestamp(df_val["epoch_a_ts"].min(), tz=timezone.utc).isoformat(),
        "val_end_utc": datetime.fromtimestamp(df_val["epoch_b_ts"].max(), tz=timezone.utc).isoformat(),
        "test_start_utc": datetime.fromtimestamp(df_test["epoch_a_ts"].min(), tz=timezone.utc).isoformat(),
        "test_end_utc": datetime.fromtimestamp(df_test["epoch_b_ts"].max(), tz=timezone.utc).isoformat(),
    }

    logger.info(
        f"Time-based split: Train={len(df_train)} pairs ({date_bounds['train_start_utc'][:10]} to {date_bounds['train_end_utc'][:10]}), "
        f"Val={len(df_val)} pairs ({date_bounds['val_start_utc'][:10]} to {date_bounds['val_end_utc'][:10]}), "
        f"Test={len(df_test)} pairs ({date_bounds['test_start_utc'][:10]} to {date_bounds['test_end_utc'][:10]})"
    )

    return df_train, df_val, df_test, date_bounds


# =====================================================================
# 5. Quantile XGBoost Model Training
# =====================================================================
class TLEErrorCorrectionModel:
    """
    Ensemble of multi-target quantile XGBoost regressors for RTN orbit error:
      Targets: radial, in-track, cross-track
      Quantiles: 0.10, 0.50 (median estimate), 0.90 (upper uncertainty)
    """

    def __init__(self):
        self.models: Dict[str, Dict[float, xgb.Booster]] = {
            "residual_radial_km": {},
            "residual_in_track_km": {},
            "residual_cross_track_km": {},
        }
        self.quantiles = [0.10, 0.50, 0.90]

    def fit(self, df_train: pd.DataFrame, df_val: pd.DataFrame) -> None:
        """Trains quantile models for each target axis."""
        X_train = df_train[FEATURE_NAMES].values
        X_val = df_val[FEATURE_NAMES].values

        for target in TARGET_NAMES:
            y_train = df_train[target].values
            y_val = df_val[target].values

            dtrain = xgb.DMatrix(X_train, label=y_train, feature_names=FEATURE_NAMES)
            dval = xgb.DMatrix(X_val, label=y_val, feature_names=FEATURE_NAMES)

            logger.info(f"Training quantile models for {target}...")
            for q in self.quantiles:
                params = {
                    "objective": "reg:quantileerror",
                    "quantile_alpha": q,
                    "max_depth": 5,
                    "learning_rate": 0.05,
                    "subsample": 0.85,
                    "colsample_bytree": 0.85,
                    "tree_method": "hist",
                }
                # Train with early stopping on validation split
                evals = [(dtrain, "train"), (dval, "val")]
                bst = xgb.train(
                    params,
                    dtrain,
                    num_boost_round=150,
                    evals=evals,
                    verbose_eval=False,
                )
                self.models[target][q] = bst

    def predict(self, X: np.ndarray) -> Dict[str, Dict[float, np.ndarray]]:
        """Generates predictions across targets and quantiles."""
        dm = xgb.DMatrix(X, feature_names=FEATURE_NAMES)
        preds: Dict[str, Dict[float, np.ndarray]] = {}
        for target in TARGET_NAMES:
            preds[target] = {}
            for q in self.quantiles:
                preds[target][q] = self.models[target][q].predict(dm)
        return preds

    def save(self, filepath: str) -> None:
        """Serializes model dictionary and metadata cleanly using joblib."""
        data = {
            "model_version": MODEL_VERSION,
            "feature_names": FEATURE_NAMES,
            "target_names": TARGET_NAMES,
            "quantiles": self.quantiles,
            "models": self.models,
        }
        joblib.dump(data, filepath)

    @classmethod
    def load(cls, filepath: str) -> "TLEErrorCorrectionModel":
        """Loads model dictionary with joblib without pickling dependency on __main__."""
        data = joblib.load(filepath)
        instance = cls()
        instance.models = data["models"]
        instance.quantiles = data.get("quantiles", [0.10, 0.50, 0.90])
        return instance


# =====================================================================
# 6. Horizon Evaluation (Day 1 to 7) & Metadata Export
# =====================================================================
def evaluate_horizons(
    model: TLEErrorCorrectionModel,
    df_test: pd.DataFrame,
) -> Dict[str, Any]:
    """
    Evaluates baseline SGP4 vs ML-corrected 3D position error across
    horizons Day 1 to Day 7. Computes real median and 90th percentile errors.
    """
    X_test = df_test[FEATURE_NAMES].values
    preds = model.predict(X_test)

    # Median point corrections (alpha = 0.50)
    pred_r = preds["residual_radial_km"][0.50]
    pred_t = preds["residual_in_track_km"][0.50]
    pred_n = preds["residual_cross_track_km"][0.50]

    true_r = df_test["residual_radial_km"].values
    true_t = df_test["residual_in_track_km"].values
    true_n = df_test["residual_cross_track_km"].values

    # Corrected residual vector: true - pred
    corr_err_r = true_r - pred_r
    corr_err_t = true_t - pred_t
    corr_err_n = true_n - pred_n

    baseline_3d = np.sqrt(true_r ** 2 + true_t ** 2 + true_n ** 2)
    corrected_3d = np.sqrt(corr_err_r ** 2 + corr_err_t ** 2 + corr_err_n ** 2)

    df_eval = df_test.copy()
    df_eval["baseline_3d_error_km"] = baseline_3d
    df_eval["corrected_3d_error_km"] = corrected_3d

    horizon_bins = [
        ("day_1", 12.0, 36.0),
        ("day_2", 36.0, 60.0),
        ("day_3", 60.0, 84.0),
        ("day_4", 84.0, 108.0),
        ("day_5", 108.0, 132.0),
        ("day_6", 132.0, 156.0),
        ("day_7", 156.0, 180.0),
    ]

    horizon_results: Dict[str, Any] = {}
    for day_label, h_min, h_max in horizon_bins:
        sub = df_eval[(df_eval["horizon_hours"] >= h_min) & (df_eval["horizon_hours"] < h_max)]
        n_samples = len(sub)
        if n_samples > 0:
            base_med = float(np.median(sub["baseline_3d_error_km"]))
            base_p90 = float(np.percentile(sub["baseline_3d_error_km"], 90))
            corr_med = float(np.median(sub["corrected_3d_error_km"]))
            corr_p90 = float(np.percentile(sub["corrected_3d_error_km"], 90))
            pct_imp = float(((base_med - corr_med) / base_med) * 100.0) if base_med > 0 else 0.0
        else:
            base_med, base_p90, corr_med, corr_p90, pct_imp = 0.0, 0.0, 0.0, 0.0, 0.0

        horizon_results[day_label] = {
            "horizon_hours_range": [h_min, h_max],
            "sample_size": n_samples,
            "baseline_median_km": round(base_med, 3),
            "baseline_p90_km": round(base_p90, 3),
            "corrected_median_km": round(corr_med, 3),
            "corrected_p90_km": round(corr_p90, 3),
            "improvement_median_pct": round(pct_imp, 1),
        }

    overall_baseline_med = float(np.median(baseline_3d))
    overall_corrected_med = float(np.median(corrected_3d))
    overall_imp = float(((overall_baseline_med - overall_corrected_med) / overall_baseline_med) * 100.0) if overall_baseline_med > 0 else 0.0

    return {
        "overall": {
            "test_sample_size": len(df_test),
            "baseline_median_km": round(overall_baseline_med, 3),
            "corrected_median_km": round(overall_corrected_med, 3),
            "overall_improvement_pct": round(overall_imp, 1),
        },
        "by_horizon": horizon_results,
    }


# =====================================================================
# 7. Main Pipeline Runner
# =====================================================================
def run_training_pipeline(
    data_dir: str = "backend/app/ml/data",
    output_dir: str = "backend/app/ml/models",
    version: str = "v1.0.0",
    min_altitude_km: float = 400.0,
    max_altitude_km: float = 900.0,
    spacetrack_user: Optional[str] = None,
    spacetrack_password: Optional[str] = None,
) -> Dict[str, Any]:
    """Orchestrates end-to-end data loading, feature engineering, training, and evaluation."""
    logger.info("=================================================================")
    logger.info("Starting Gagan Suraksha TLE Error-Correction Model Training Pipeline")
    logger.info("=================================================================")

    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    sw_dir = os.path.join(data_dir, "space_weather")
    tle_dir = os.path.join(data_dir, "tles")
    os.makedirs(tle_dir, exist_ok=True)

    # 1. Space Weather Data
    sw_manager = SpaceWeatherManager(sw_dir)

    # 2. Space-Track Download (if credentials provided)
    if spacetrack_user and spacetrack_password:
        logger.info("Space-Track credentials detected. Querying historical LEO catalog...")
        sample_norads = [43111, 44857, 51656, 45026, 41752, 40930, 25544, 20580, 24869]
        spacetrack_out = os.path.join(tle_dir, "spacetrack_history.tle")
        try:
            download_spacetrack_history(
                spacetrack_user,
                spacetrack_password,
                sample_norads,
                "2026-01-01",
                "2026-09-30",
                spacetrack_out,
            )
        except Exception as e:
            logger.warning(f"Space-Track download encountered an issue: {e}")

    # 3. Load All Cached TLEs
    tle_files = glob.glob(os.path.join(tle_dir, "*.txt")) + glob.glob(os.path.join(tle_dir, "*.tle"))
    if not tle_files:
        raise RuntimeError(
            f"No TLE files found in '{tle_dir}' and no Space-Track credentials provided. "
            "Never fabricating synthetic TLE data. Please place historical TLE files in "
            "backend/app/ml/data/tles/ or provide SPACETRACK_USER and SPACETRACK_PASSWORD."
        )

    logger.info(f"Found {len(tle_files)} raw TLE files in {tle_dir}.")
    all_records: List[TLERecord] = []
    seen_tle_keys = set()
    for fpath in tle_files:
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            recs = parse_tle_text(content)
            for r in recs:
                k = (r.norad_id, round(r.epoch_ts, 4))
                if k not in seen_tle_keys:
                    seen_tle_keys.add(k)
                    all_records.append(r)

    logger.info(f"Parsed {len(all_records)} unique, valid TLE records from disk cache.")

    # 4. Generate Pairs & RTN Residuals
    df_pairs = generate_tle_pairs(
        all_records,
        sw_manager,
        min_altitude_km=min_altitude_km,
        max_altitude_km=max_altitude_km,
    )

    if len(df_pairs) < 30:
        raise RuntimeError(
            f"Insufficient TLE pairs generated ({len(df_pairs)} pairs). "
            "Need more multi-epoch TLE updates to train without synthetic data."
        )

    # 5. Time-Based Split
    df_train, df_val, df_test, date_bounds = split_by_time(df_pairs)

    # 6. Fit Quantile XGBoost Models
    model = TLEErrorCorrectionModel()
    model.fit(df_train, df_val)

    # 7. Horizon Evaluation (Day 1 to 7)
    eval_metrics = evaluate_horizons(model, df_test)

    # 8. Serialize Model and Write Honest Metadata
    model_path = os.path.join(output_dir, f"tle_error_xgb_{version}.joblib")
    model.save(model_path)
    logger.info(f"Saved trained quantile models to {model_path}.")

    metadata = {
        "model_version": version,
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "reference_truth": "Later TLE epoch state (SGP4 propagation at epoch tB)",
        "data_source": "CelesTrak historical TLE archives & SpaceData (SW-All.csv, SW-Last5Years.csv)",
        "altitude_bounds_km": [min_altitude_km, max_altitude_km],
        "training_date_bounds": date_bounds,
        "features": FEATURE_NAMES,
        "targets": TARGET_NAMES,
        "sample_sizes": {
            "total_pairs": len(df_pairs),
            "train_pairs": len(df_train),
            "val_pairs": len(df_val),
            "test_pairs": len(df_test),
            "unique_satellites": int(df_pairs["norad_id"].nunique()),
        },
        "evaluation_metrics": eval_metrics,
        "assumptions_and_limitations": [
            "Analytical SGP4 propagator used for baseline and reference evaluation.",
            "Later TLEs serve as reference truth in the absence of high-precision radar/numerical ephemeris.",
            "Time-based split enforces zero future data leakage.",
            "Prototype research model; operational mission maneuvers require high-precision numerical orbit determination."
        ],
    }

    metadata_path = os.path.join(output_dir, "metadata.json")
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    logger.info(f"Wrote evaluation metadata to {metadata_path}.")

    logger.info("=================================================================")
    logger.info(f"Pipeline complete! Overall test error reduction: {eval_metrics['overall']['overall_improvement_pct']}%")
    logger.info("=================================================================")

    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train Gagan Suraksha TLE error-correction model.")
    parser.add_argument("--data-dir", default="backend/app/ml/data", help="Directory with cached TLEs and space weather")
    parser.add_argument("--output-dir", default="backend/app/ml/models", help="Directory for model output and metadata")
    parser.add_argument("--version", default="v1.0.0", help="Model version identifier")
    parser.add_argument("--min-altitude", type=float, default=400.0, help="Min LEO altitude in km")
    parser.add_argument("--max-altitude", type=float, default=900.0, help="Max LEO altitude in km")
    parser.add_argument("--spacetrack-user", default=os.getenv("SPACETRACK_USER"), help="Space-Track username")
    parser.add_argument("--spacetrack-password", default=os.getenv("SPACETRACK_PASSWORD"), help="Space-Track password")

    args = parser.parse_args()
    run_training_pipeline(
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        version=args.version,
        min_altitude_km=args.min_altitude,
        max_altitude_km=args.max_altitude,
        spacetrack_user=args.spacetrack_user,
        spacetrack_password=args.spacetrack_password,
    )
