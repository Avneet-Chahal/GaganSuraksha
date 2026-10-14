"""
Gagan Suraksha Risk Assessment Service.
Computes collision probability Pc twice:
1. Classical raw Foster 2D from SGP4 state and assumed covariance.
2. ML-corrected Foster 2D using quantile error-corrected state and covariance built from the quantile spread.
Applies IsotonicRegression probability calibration to the ML-corrected Pc.
Derives total miss distance strictly from RTN components (sqrt(R^2 + T^2 + N^2)).
"""

import logging
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple ,Union

import joblib
import numpy as np

from backend.services.sgp4_service import parse_iso_datetime
from ml.predict import correct_state

logger = logging.getLogger("gagan_suraksha.risk")

_CALIBRATOR_INSTANCE = None
_CALIBRATOR_LOAD_ATTEMPTED = False


def compute_total_miss_km(
    radial_km: float,
    in_track_km: float,
    cross_track_km: float,
) -> float:
    """
    Computes total miss distance from orthogonal RTN components:
    total_miss = sqrt(radial^2 + in_track^2 + cross_track^2)
    Ensures mathematical agreement everywhere.
    """
    return float(math.sqrt(radial_km**2 + in_track_km**2 + cross_track_km**2))


def decompose_rtn(
    r1: np.ndarray,
    v1: np.ndarray,
    r2: np.ndarray,
    v2: np.ndarray,
) -> Tuple[float, float, float, float, float]:
    """
    Decomposes relative miss vector into the primary satellite's RTN frame:
    - Radial: R_hat = r1 / ||r1||
    - Cross-track (normal): N_hat = (r1 x v1) / ||r1 x v1||
    - In-track: T_hat = N_hat x R_hat
    Returns: (radial_miss_km, in_track_miss_km, cross_track_miss_km, total_miss_km, rel_vel_km_s)
    """
    r1_norm = np.linalg.norm(r1)
    if r1_norm < 1e-6:
        r_hat = np.array([1.0, 0.0, 0.0])
    else:
        r_hat = r1 / r1_norm

    h = np.cross(r1, v1)
    h_norm = np.linalg.norm(h)
    if h_norm < 1e-6:
        n_hat = np.array([0.0, 0.0, 1.0])
    else:
        n_hat = h / h_norm

    t_hat = np.cross(n_hat, r_hat)
    t_norm = np.linalg.norm(t_hat)
    if t_norm > 1e-6:
        t_hat = t_hat / t_norm
    else:
        t_hat = np.array([0.0, 1.0, 0.0])

    delta_r = r2 - r1
    delta_v = v2 - v1

    miss_r = abs(float(np.dot(delta_r, r_hat)))
    miss_t = abs(float(np.dot(delta_r, t_hat)))
    miss_n = abs(float(np.dot(delta_r, n_hat)))

    # Compute total miss directly from RTN components
    total_miss = compute_total_miss_km(miss_r, miss_t, miss_n)
    rel_vel = float(np.linalg.norm(delta_v))

    return miss_r, miss_t, miss_n, total_miss, rel_vel


def estimate_satellite_covariance(
    satellite_type: str,
    tle_epoch_iso: str,
    tca_dt: datetime,
) -> Tuple[float, float, float]:
    """
    Estimates 1-sigma positional uncertainty (radial, in-track, cross-track in meters).
    TLEs do not include covariance; uncertainty increases with TLE age and propagation horizon.
    """
    try:
        epoch_dt = parse_iso_datetime(tle_epoch_iso)
        age_days = max(0.1, abs((tca_dt - epoch_dt).total_seconds()) / 86400.0)
    except Exception:
        age_days = 1.0

    is_debris = satellite_type.upper() in ("DEBRIS", "ROCKET_BODY", "UNKNOWN")
    base_r = 40.0 if is_debris else 15.0
    base_t = 150.0 if is_debris else 50.0
    base_n = 60.0 if is_debris else 20.0

    # In-track uncertainty grows fastest due to unmodeled drag and solar pressure
    sigma_r = base_r * (1.0 + 0.20 * age_days)
    sigma_t = base_t * (1.0 + 0.60 * (age_days**1.2))
    sigma_n = base_n * (1.0 + 0.25 * age_days)

    return round(sigma_r, 1), round(sigma_t, 1), round(sigma_n, 1)


def compute_foster_2d_pc(
    radial_miss_km: float,
    in_track_miss_km: float,
    cross_track_miss_km: float,
    primary_sigmas_m: Tuple[float, float, float],
    secondary_sigmas_m: Tuple[float, float, float],
    hard_body_radius_m: float = 10.0,
) -> float:
    """
    Computes Foster 2D collision probability in the encounter plane.
    Monotonically decreases with increasing miss distance.
    """
    # Convert meters to km
    sig_r1_km, sig_t1_km, sig_n1_km = [s / 1000.0 for s in primary_sigmas_m]
    sig_r2_km, sig_t2_km, sig_n2_km = [s / 1000.0 for s in secondary_sigmas_m]
    hbr_km = hard_body_radius_m / 1000.0

    # Combined root-sum-squared uncertainties in principal directions
    comb_sig_r = math.sqrt(sig_r1_km**2 + sig_r2_km**2)
    comb_sig_t = math.sqrt(sig_t1_km**2 + sig_t2_km**2)
    comb_sig_n = math.sqrt(sig_n1_km**2 + sig_n2_km**2)

    # Encounter plane variance product (radial and along-track components)
    det = comb_sig_r * comb_sig_t
    if det < 1e-12:
        return 0.0

    # Quadratic exponent in encounter plane
    quad = (radial_miss_km / comb_sig_r)**2 + (in_track_miss_km / comb_sig_t)**2 + (cross_track_miss_km / comb_sig_n)**2 * 0.1
    exponent = -0.5 * quad

    # Foster 2D circular integral approximation
    hbr_area_factor = (hbr_km**2) / (2.0 * det)
    pc = hbr_area_factor * math.exp(exponent)

    return min(1.0, max(0.0, pc))


def classify_risk(
    pc: float,
    miss_distance_km: float,
) -> Tuple[str, str]:
    """
    Evaluates riskLevel and recommendedAction according to mission safety rules:
    - CRITICAL: Pc >= 1e-4 or miss < 1.0 km -> MANEUVER_RECOMMENDED
    - WARNING: Pc >= 1e-5 or miss < 5.0 km -> WAIT_MONITOR
    - NOMINAL: otherwise -> WAIT_MONITOR
    """
    if pc >= 1.0e-4 or miss_distance_km < 1.0:
        return "CRITICAL", "MANEUVER_RECOMMENDED"
    if pc >= 1.0e-5 or miss_distance_km < 5.0:
        return "WARNING", "WAIT_MONITOR"
    return "NOMINAL", "WAIT_MONITOR"


def load_pc_calibrator(model_dir: Optional[Union[str, Path]] = None) -> Any:
    """Loads the fitted IsotonicRegression calibrator from disk."""
    global _CALIBRATOR_INSTANCE, _CALIBRATOR_LOAD_ATTEMPTED

    if model_dir is not None:
        p = Path(model_dir) / "pc_calibrator.joblib"
        if p.exists():
            try:
                return joblib.load(p)
            except Exception as e:
                logger.warning("Error loading calibrator from %s: %e", p, e)
                return None
        return None

    if _CALIBRATOR_LOAD_ATTEMPTED:
        return _CALIBRATOR_INSTANCE

    _CALIBRATOR_LOAD_ATTEMPTED = True
    candidates = [
        Path("backend/app/ml/models/pc_calibrator.joblib"),
        Path(__file__).parent.parent / "backend/app/ml/models/pc_calibrator.joblib",
        Path("ml/models/pc_calibrator.joblib"),
    ]
    for c in candidates:
        if c.exists():
            try:
                _CALIBRATOR_INSTANCE = joblib.load(c)
                logger.info("Loaded IsotonicRegression Pc calibrator from %s.", c)
                return _CALIBRATOR_INSTANCE
            except Exception as exc:
                logger.warning("Failed loading calibrator from %s: %s", c, exc)

    logger.info("No pc_calibrator.joblib found; calibrator is None.")
    return None


def reset_pc_calibrator() -> None:
    """Resets cached calibrator (useful in testing)."""
    global _CALIBRATOR_INSTANCE, _CALIBRATOR_LOAD_ATTEMPTED
    _CALIBRATOR_INSTANCE = None
    _CALIBRATOR_LOAD_ATTEMPTED = False


_SENTINEL = object()


def calibrate_pc(
    pc_uncalibrated: float,
    calibrator: Any = _SENTINEL,
) -> Tuple[float, bool]:
    """
    Applies IsotonicRegression to the uncalibrated Pc.
    If no calibrator is available, returns (pc_uncalibrated, False).
    """
    cal = load_pc_calibrator() if calibrator is _SENTINEL else calibrator
    if cal is None:
        return float(pc_uncalibrated), False

    try:
        calibrated_val = float(cal.predict([pc_uncalibrated])[0])
        return min(1.0, max(0.0, calibrated_val)), True
    except Exception as exc:
        logger.warning("Calibration prediction failed: %s. Returning uncalibrated Pc.", exc)
        return float(pc_uncalibrated), False


def evaluate_conjunction_risk(
    primary_sat: Any,
    secondary_sat: Any,
    tca_dt: datetime,
    r1: np.ndarray,
    v1: np.ndarray,
    r2: np.ndarray,
    v2: np.ndarray,
    weather: Optional[Dict[str, float]] = None,
    hard_body_radius_m: float = 10.0,
    calibrator: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Complete conjunction risk evaluation:
    1. Computes raw miss vector and Foster 2D pc_raw from SGP4 states.
    2. Corrects states with ML quantile model and builds covariance from quantile spread.
    3. Computes pc_ml from corrected states and ML-derived covariance.
    4. Calibrates pc_ml with IsotonicRegression -> pc_ml_calibrated.
    5. Computes total miss distance from RTN components.
    """
    # 1. Raw SGP4 RTN Decomposition
    raw_r, raw_t, raw_n, raw_total_miss, raw_rel_vel = decompose_rtn(r1, v1, r2, v2)

    # Assumed empirical covariances
    p_type = getattr(primary_sat, "type", "PAYLOAD")
    s_type = getattr(secondary_sat, "type", "DEBRIS")
    p_epoch = getattr(primary_sat, "tle_epoch", tca_dt.isoformat())
    s_epoch = getattr(secondary_sat, "tle_epoch", tca_dt.isoformat())

    cov1_raw = estimate_satellite_covariance(p_type, p_epoch, tca_dt)
    cov2_raw = estimate_satellite_covariance(s_type, s_epoch, tca_dt)

    pc_raw = compute_foster_2d_pc(
        radial_miss_km=raw_r,
        in_track_miss_km=raw_t,
        cross_track_miss_km=raw_n,
        primary_sigmas_m=cov1_raw,
        secondary_sigmas_m=cov2_raw,
        hard_body_radius_m=hard_body_radius_m,
    )

    # 2. ML State Correction & Quantile Covariance
    corr1 = correct_state(
        sat_state=(r1, v1),
        tle_epoch=p_epoch,
        t_target=tca_dt,
        weather=weather,
    )
    corr2 = correct_state(
        sat_state=(r2, v2),
        tle_epoch=s_epoch,
        t_target=tca_dt,
        weather=weather,
    )

    ml_available = corr1.ml_available and corr2.ml_available
    model_version = corr1.model_version or corr2.model_version or "v1.0.0"

    # Geometry of conjunction event at TCA (derived strictly from RTN components)
    final_r, final_t, final_n = raw_r, raw_t, raw_n
    final_total_miss = raw_total_miss
    final_rel_vel = raw_rel_vel

    if ml_available:
        r1_c = corr1.corrected_position
        r2_c = corr2.corrected_position
        cov1_ml = corr1.bounds["sigma_rtn_m"]
        cov2_ml = corr2.bounds["sigma_rtn_m"]

        ml_r, ml_t, ml_n, ml_total_miss, ml_rel_vel = decompose_rtn(r1_c, v1, r2_c, v2)
        pc_ml = compute_foster_2d_pc(
            radial_miss_km=ml_r,
            in_track_miss_km=ml_t,
            cross_track_miss_km=ml_n,
            primary_sigmas_m=cov1_ml,
            secondary_sigmas_m=cov2_ml,
            hard_body_radius_m=hard_body_radius_m,
        )
        final_cov1 = cov1_ml
        final_cov2 = cov2_ml
    else:
        pc_ml = pc_raw
        final_cov1 = cov1_raw
        final_cov2 = cov2_raw

    # 3. Calibration
    pc_ml_calibrated, is_calibrated = calibrate_pc(pc_ml, calibrator=calibrator)

    # 4. Classify Risk using calibrated probability
    risk_level, rec_action = classify_risk(pc_ml_calibrated, final_total_miss)

    return {
        "miss_distance_km": round(final_total_miss, 3),
        "radial_miss_km": round(final_r, 3),
        "in_track_miss_km": round(final_t, 3),
        "cross_track_miss_km": round(final_n, 3),
        "relative_velocity_km_s": round(final_rel_vel, 2),
        "pc_raw": float(f"{pc_raw:.3e}"),
        "pc_ml": float(f"{pc_ml:.3e}"),
        "pc_ml_calibrated": float(f"{pc_ml_calibrated:.3e}"),
        "is_calibrated": is_calibrated,
        "ml_available": ml_available,
        "model_version": model_version,
        "risk_level": risk_level,
        "recommended_action": rec_action,
        "primary_covariance_rtn_m": final_cov1,
        "secondary_covariance_rtn_m": final_cov2,
        "raw_geometry": {
            "radial_km": round(raw_r, 3),
            "in_track_km": round(raw_t, 3),
            "cross_track_km": round(raw_n, 3),
            "total_miss_km": round(raw_total_miss, 3),
            "primary_covariance_rtn_m": cov1_raw,
            "secondary_covariance_rtn_m": cov2_raw,
        },
    }
