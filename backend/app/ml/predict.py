"""
Gagan Suraksha ML Inference Service.
Loads quantile XGBoost orbit error-correction models as a singleton and exposes
correct_state(sat_state, tle_epoch, t_target, weather).
Gracefully falls back to raw SGP4 if model files are missing or unreadable.
"""

import json
import logging
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import joblib
import numpy as np
import xgboost as xgb

logger = logging.getLogger("gagan_suraksha.ml.predict")

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


class CorrectedStateResult(dict):
    """Dictionary subclass supporting attribute-style access for convenience."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'CorrectedStateResult' object has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


class StatePredictor:
    """Singleton predictor holding trained quantile XGBoost models in memory."""

    _instance: Optional["StatePredictor"] = None

    def __init__(self, model_dir: Optional[Union[str, Path]] = None):
        self.model_dir = self._resolve_model_dir(model_dir)
        self.models: Dict[str, Dict[float, xgb.Booster]] = {}
        self.metadata: Dict[str, Any] = {}
        self.model_version: Optional[str] = None
        self.ml_available: bool = False
        self._load_models()
        StatePredictor._instance = self

    @classmethod
    def get_instance(cls, model_dir: Optional[Union[str, Path]] = None) -> "StatePredictor":
        """Returns the singleton predictor instance, initializing once."""
        if cls._instance is None:
            cls._instance = cls(model_dir=model_dir)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Resets singleton (used in testing fallback behaviors)."""
        cls._instance = None

    def _resolve_model_dir(self, override: Optional[Union[str, Path]]) -> Path:
        if override:
            return Path(override)
        env_path = os.getenv("GAGAN_ML_MODEL_DIR")
        if env_path:
            return Path(env_path)

        candidates = [
            Path(__file__).parent / "models",
            Path("backend/app/ml/models"),
            Path("ml/models"),
            Path("../backend/app/ml/models"),
        ]
        for c in candidates:
            if c.exists() and (c / "metadata.json").exists():
                return c.resolve()
        # Default to standard path
        return (Path(__file__).parent / "models").resolve()

    def _load_models(self) -> None:
        """Loads joblib model artifact and metadata.json. Sets ml_available=False on failure."""
        try:
            meta_path = self.model_dir / "metadata.json"
            if meta_path.exists():
                with open(meta_path, "r", encoding="utf-8") as f:
                    self.metadata = json.load(f)
                self.model_version = self.metadata.get("model_version", "v1.0.0")

            # Find joblib model file
            model_files = list(self.model_dir.glob("*.joblib"))
            if not model_files:
                logger.warning(
                    "No .joblib model files found in '%s'. Falling back to raw SGP4 (ml_available=False).",
                    self.model_dir,
                )
                self.ml_available = False
                return

            # Prefer file matching model_version if available
            chosen_file = model_files[0]
            for mf in model_files:
                if self.model_version and self.model_version in mf.name:
                    chosen_file = mf
                    break

            logger.info("Loading ML TLE error-correction model from: %s", chosen_file)
            data = joblib.load(chosen_file)

            if isinstance(data, dict) and "models" in data:
                self.models = data["models"]
            elif hasattr(data, "models"):
                self.models = data.models
            else:
                logger.warning("Unrecognized model artifact format in %s.", chosen_file)
                self.ml_available = False
                return

            self.ml_available = True
            logger.info(
                "ML model loaded successfully (version: %s, targets: %s).",
                self.model_version,
                list(self.models.keys()),
            )
        except Exception as exc:
            logger.warning(
                "Error loading ML model from '%s': %s. Falling back to raw SGP4 (ml_available=False).",
                self.model_dir,
                exc,
            )
            self.ml_available = False

    def predict_rtn_residuals(
        self,
        features_dict: Dict[str, float],
    ) -> Dict[str, Dict[float, float]]:
        """
        Runs XGBoost quantile inference for a single observation feature vector.
        Returns {target: {0.10: val, 0.50: val, 0.90: val}}.
        """
        if not self.ml_available:
            return {t: {0.10: 0.0, 0.50: 0.0, 0.90: 0.0} for t in TARGET_NAMES}

        x_row = np.array([[float(features_dict.get(f, 0.0)) for f in FEATURE_NAMES]], dtype=np.float32)
        dm = xgb.DMatrix(x_row, feature_names=FEATURE_NAMES)

        preds: Dict[str, Dict[float, float]] = {}
        for target in TARGET_NAMES:
            preds[target] = {}
            target_models = self.models.get(target, {})
            for q, booster in target_models.items():
                p = float(booster.predict(dm)[0])
                preds[target][float(q)] = p
        return preds


def parse_timestamp_utc(val: Any) -> datetime:
    """Safely converts string, numeric timestamp, or datetime into timezone-aware UTC datetime."""
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val.astimezone(timezone.utc)
    if isinstance(val, (int, float)):
        return datetime.fromtimestamp(val, tz=timezone.utc)
    if isinstance(val, str):
        cleaned = val.replace("Z", "+00:00").strip()
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    raise ValueError(f"Cannot parse timestamp from {val!r}")


def _unpack_sat_state(
    sat_state: Any,
) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    """
    Extracts (r, v, metadata) from flexible sat_state structures:
    - (r, v) tuple of 3D arrays
    - 6-element list/array [x, y, z, vx, vy, vz]
    - dict with keys 'r', 'v' or 'x', 'y', 'z', etc.
    - object with attributes r, v or x, y, z
    """
    meta: Dict[str, Any] = {}

    if isinstance(sat_state, dict):
        if "r" in sat_state and "v" in sat_state:
            r = np.array(sat_state["r"], dtype=np.float64)
            v = np.array(sat_state["v"], dtype=np.float64)
        elif "position" in sat_state and "velocity" in sat_state:
            r = np.array(sat_state["position"], dtype=np.float64)
            v = np.array(sat_state["velocity"], dtype=np.float64)
        elif "x" in sat_state and "y" in sat_state and "z" in sat_state:
            r = np.array([sat_state["x"], sat_state["y"], sat_state["z"]], dtype=np.float64)
            vx = sat_state.get("vx", 0.0)
            vy = sat_state.get("vy", 0.0)
            vz = sat_state.get("vz", 0.0)
            v = np.array([vx, vy, vz], dtype=np.float64)
        else:
            raise ValueError(f"Cannot extract position/velocity from sat_state dict: {sat_state.keys()}")
        meta.update(sat_state)

    elif isinstance(sat_state, (tuple, list)):
        if len(sat_state) == 2 and hasattr(sat_state[0], "__len__") and len(sat_state[0]) == 3:
            r = np.array(sat_state[0], dtype=np.float64)
            v = np.array(sat_state[1], dtype=np.float64)
        elif len(sat_state) == 6:
            r = np.array(sat_state[:3], dtype=np.float64)
            v = np.array(sat_state[3:], dtype=np.float64)
        elif len(sat_state) == 3:
            r = np.array(sat_state, dtype=np.float64)
            v = np.zeros(3, dtype=np.float64)
        else:
            raise ValueError(f"Unrecognized sat_state sequence length {len(sat_state)}")

    elif hasattr(sat_state, "r") and hasattr(sat_state, "v"):
        r = np.array(sat_state.r, dtype=np.float64)
        v = np.array(sat_state.v, dtype=np.float64)
    elif hasattr(sat_state, "x") and hasattr(sat_state, "y") and hasattr(sat_state, "z"):
        r = np.array([sat_state.x, sat_state.y, sat_state.z], dtype=np.float64)
        v = np.array(
            [getattr(sat_state, "vx", 0.0), getattr(sat_state, "vy", 0.0), getattr(sat_state, "vz", 0.0)],
            dtype=np.float64,
        )
    else:
        raise ValueError(f"Unsupported sat_state type: {type(sat_state)}")

    return r, v, meta


def correct_state(
    sat_state: Any,
    tle_epoch: Any,
    t_target: Any,
    weather: Optional[Dict[str, float]] = None,
    predictor: Optional["StatePredictor"] = None,
) -> CorrectedStateResult:
    """
    Applies the ML quantile error-correction model to an SGP4 propagated state.

    Parameters:
    -----------
    sat_state: (r, v) state vector (km, km/s) or object/dict.
    tle_epoch: TLE epoch datetime, ISO string, or timestamp.
    t_target: Target propagation datetime, ISO string, or timestamp.
    weather: Optional dictionary with space-weather parameters:
             f107_daily, f107_81d_avg, kp_epoch, ap_epoch, kp_mean_horizon, ap_mean_horizon.

    Returns:
    --------
    CorrectedStateResult containing:
      - corrected_position: np.ndarray (x, y, z) in km
      - raw_position: np.ndarray (x, y, z) in km
      - velocity: np.ndarray (vx, vy, vz) in km/s
      - bounds: {
            "p10": [r_10, t_10, n_10],
            "p50": [r_50, t_50, n_50],
            "p90": [r_90, t_90, n_90],
            "error_3d_p10_km": float,
            "error_3d_p50_km": float,
            "error_3d_p90_km": float,
            "sigma_rtn_m": (sigma_r_m, sigma_t_m, sigma_n_m),
        }
      - ml_available: bool (False if models are missing/unloaded)
      - model_version: Optional[str]
      - correction_vector_eci_km: np.ndarray (ECI shift vector)
    """
    try:
        r_raw, v_raw, meta = _unpack_sat_state(sat_state)
        epoch_dt = parse_timestamp_utc(tle_epoch)
        target_dt = parse_timestamp_utc(t_target)
    except Exception as exc:
        logger.error("Failed to parse inputs in correct_state: %s", exc)
        # Fallback without crashing
        zero3 = np.zeros(3, dtype=np.float64)
        return CorrectedStateResult({
            "corrected_position": zero3,
            "raw_position": zero3,
            "velocity": zero3,
            "bounds": {
                "p10": [0.0, 0.0, 0.0],
                "p50": [0.0, 0.0, 0.0],
                "p90": [0.0, 0.0, 0.0],
                "error_3d_p10_km": 0.0,
                "error_3d_p50_km": 0.0,
                "error_3d_p90_km": 0.0,
                "sigma_rtn_m": (15.0, 50.0, 20.0),
            },
            "ml_available": False,
            "model_version": None,
            "correction_vector_eci_km": zero3,
        })

    predictor = predictor or StatePredictor.get_instance()

    # If ML model is unavailable, return raw position directly
    if not predictor.ml_available:
        return CorrectedStateResult({
            "corrected_position": r_raw.copy(),
            "raw_position": r_raw.copy(),
            "velocity": v_raw.copy(),
            "bounds": {
                "p10": [0.0, 0.0, 0.0],
                "p50": [0.0, 0.0, 0.0],
                "p90": [0.0, 0.0, 0.0],
                "error_3d_p10_km": 0.0,
                "error_3d_p50_km": 0.0,
                "error_3d_p90_km": 0.0,
                "sigma_rtn_m": (15.0, 50.0, 20.0),
            },
            "ml_available": False,
            "model_version": None,
            "correction_vector_eci_km": np.zeros(3, dtype=np.float64),
        })

    # 1. Compute propagation horizon
    delta_sec = (target_dt - epoch_dt).total_seconds()
    horizon_hours = max(0.1, abs(delta_sec) / 3600.0)

    # 2. Extract orbital parameters
    r_norm = float(np.linalg.norm(r_raw))
    alt_km = meta.get("altitude_km", r_norm - 6378.137)

    # Specific angular momentum vector h = r x v
    h_vec = np.cross(r_raw, v_raw)
    h_norm = float(np.linalg.norm(h_vec))

    if "inclination_deg" in meta:
        inc_deg = float(meta["inclination_deg"])
    elif h_norm > 1e-6:
        inc_deg = float(math.degrees(math.acos(np.clip(h_vec[2] / h_norm, -1.0, 1.0))))
    else:
        inc_deg = 51.6

    ecc = float(meta.get("eccentricity", 0.001))
    bstar = float(meta.get("bstar", 0.0001))

    # Mean motion in rev/day from vis-viva or meta
    if "mean_motion_rev_day" in meta:
        mm = float(meta["mean_motion_rev_day"])
    elif r_norm > 1000.0:
        mu = 398600.4418
        n_rad_s = math.sqrt(mu / (r_norm**3))
        mm = float(n_rad_s * 86400.0 / (2.0 * math.pi))
    else:
        mm = 15.0

    obj_type_code = float(meta.get("object_type_code", 1))

    # 3. Space Weather Features
    w = weather or {}
    f107_d = float(w.get("f107_daily", 120.0))
    f107_81 = float(w.get("f107_81d_avg", w.get("f107_81d", 120.0)))
    kp_ep = float(w.get("kp_epoch", w.get("kp", 2.5)))
    ap_ep = float(w.get("ap_epoch", w.get("ap", 10.0)))
    kp_h = float(w.get("kp_mean_horizon", kp_ep))
    ap_h = float(w.get("ap_mean_horizon", ap_ep))

    features = {
        "horizon_hours": horizon_hours,
        "altitude_km": alt_km,
        "inclination_deg": inc_deg,
        "eccentricity": ecc,
        "bstar": bstar,
        "mean_motion_rev_day": mm,
        "f107_daily": f107_d,
        "f107_81d_avg": f107_81,
        "kp_epoch": kp_ep,
        "ap_epoch": ap_ep,
        "kp_mean_horizon": kp_h,
        "ap_mean_horizon": ap_h,
        "object_type_code": obj_type_code,
    }

    # 4. Predict RTN Residuals
    preds = predictor.predict_rtn_residuals(features)

    res_r_10 = preds["residual_radial_km"].get(0.10, 0.0)
    res_r_50 = preds["residual_radial_km"].get(0.50, 0.0)
    res_r_90 = preds["residual_radial_km"].get(0.90, 0.0)

    res_t_10 = preds["residual_in_track_km"].get(0.10, 0.0)
    res_t_50 = preds["residual_in_track_km"].get(0.50, 0.0)
    res_t_90 = preds["residual_in_track_km"].get(0.90, 0.0)

    res_n_10 = preds["residual_cross_track_km"].get(0.10, 0.0)
    res_n_50 = preds["residual_cross_track_km"].get(0.50, 0.0)
    res_n_90 = preds["residual_cross_track_km"].get(0.90, 0.0)

    # 5. Unit vectors for RTN frame in ECI
    r_hat = r_raw / r_norm if r_norm > 1e-6 else np.array([1.0, 0.0, 0.0])
    n_hat = h_vec / h_norm if h_norm > 1e-6 else np.array([0.0, 0.0, 1.0])
    t_hat = np.cross(n_hat, r_hat)
    t_norm = np.linalg.norm(t_hat)
    if t_norm > 1e-6:
        t_hat = t_hat / t_norm
    else:
        t_hat = np.array([0.0, 1.0, 0.0])

    # 6. Apply median correction: r_corrected = r_prop - delta_r_50
    # Note: residual was defined as r_prop - r_true, so r_true ~ r_prop - res_pred
    delta_r_50_eci = res_r_50 * r_hat + res_t_50 * t_hat + res_n_50 * n_hat
    r_corrected = r_raw - delta_r_50_eci

    # 7. Uncertainty estimation from quantile spread (90th - 10th percentile / 2.5631 sigma)
    # Gaussian 10-90 spread is 2.5631 sigma
    sigma_r_km = max(0.015, abs(res_r_90 - res_r_10) / 2.5631)
    sigma_t_km = max(0.050, abs(res_t_90 - res_t_10) / 2.5631)
    sigma_n_km = max(0.020, abs(res_n_90 - res_n_10) / 2.5631)

    sigma_r_m = round(sigma_r_km * 1000.0, 1)
    sigma_t_m = round(sigma_t_km * 1000.0, 1)
    sigma_n_m = round(sigma_n_km * 1000.0, 1)

    err_3d_p10 = float(math.sqrt(res_r_10**2 + res_t_10**2 + res_n_10**2))
    err_3d_p50 = float(math.sqrt(res_r_50**2 + res_t_50**2 + res_n_50**2))
    err_3d_p90 = float(math.sqrt(res_r_90**2 + res_t_90**2 + res_n_90**2))

    return CorrectedStateResult({
        "corrected_position": r_corrected,
        "raw_position": r_raw.copy(),
        "velocity": v_raw.copy(),
        "bounds": {
            "p10": [round(res_r_10, 4), round(res_t_10, 4), round(res_n_10, 4)],
            "p50": [round(res_r_50, 4), round(res_t_50, 4), round(res_n_50, 4)],
            "p90": [round(res_r_90, 4), round(res_t_90, 4), round(res_n_90, 4)],
            "error_3d_p10_km": round(err_3d_p10, 4),
            "error_3d_p50_km": round(err_3d_p50, 4),
            "error_3d_p90_km": round(err_3d_p90, 4),
            "sigma_rtn_m": (sigma_r_m, sigma_t_m, sigma_n_m),
        },
        "ml_available": True,
        "model_version": predictor.model_version,
        "correction_vector_eci_km": delta_r_50_eci,
    })
