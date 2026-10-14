import logging
import math
from datetime import datetime, timezone, timedelta
from typing import List, Tuple, Optional
import numpy as np
from sgp4.api import Satrec, SatrecArray
from sqlalchemy.orm import Session
from sqlalchemy import select, delete

from backend.models.db_models import SatelliteModel, ConjunctionModel
from backend.services.sgp4_service import parse_iso_datetime

logger = logging.getLogger("gagan_suraksha.screening")

# Safe minimization: use scipy if permissible, else Golden Section search fallback
try:
    from scipy.optimize import minimize_scalar
except Exception:
    def minimize_scalar(f, bounds, method="bounded", options=None):  # type: ignore[misc]
        a, b = float(bounds[0]), float(bounds[1])
        tol = options.get("xatol", 1e-4) if options else 1e-4
        phi = (math.sqrt(5.0) - 1.0) / 2.0  # 0.6180339887
        x1 = a + (1.0 - phi) * (b - a)
        x2 = a + phi * (b - a)
        f1 = f(x1)
        f2 = f(x2)
        while (b - a) > tol:
            if f1 < f2:
                b = x2
                x2 = x1
                f2 = f1
                x1 = a + (1.0 - phi) * (b - a)
                f1 = f(x1)
            else:
                a = x1
                x1 = x2
                f1 = f2
                x2 = a + phi * (b - a)
                f2 = f(x2)
        x_opt = (a + b) / 2.0
        return type("OptimizeResult", (), {"x": x_opt, "fun": f(x_opt)})()


def check_altitude_overlap(
    perigee1_km: float,
    apogee1_km: float,
    perigee2_km: float,
    apogee2_km: float,
    buffer_km: float = 20.0,
) -> bool:
    """
    Coarse filter: returns True if orbit altitude ranges overlap within buffer_km.
    Rejects pairs that cannot geometrically intersect.
    """
    if (perigee1_km - buffer_km) > (apogee2_km + buffer_km):
        return False
    if (perigee2_km - buffer_km) > (apogee1_km + buffer_km):
        return False
    return True


def coarse_search_candidates(
    satrec1: Satrec,
    satrec2: Satrec,
    start_dt: datetime,
    duration_days: float = 7.0,
    step_seconds: float = 60.0,
    threshold_distance_km: float = 50.0,
) -> List[int]:
    """
    Propagates a satellite pair across duration_days at step_seconds intervals
    using sgp4's vectorized SatrecArray and returns indices of candidate steps where distance < 50 km.
    """
    total_seconds = duration_days * 86400.0
    n_steps = int(total_seconds // step_seconds) + 1

    start_ts = start_dt.timestamp()
    times_sec = np.arange(n_steps, dtype=np.float64) * step_seconds
    ts_array = start_ts + times_sec

    # Julian Date conversion: epoch 1970-01-01 00:00:00 UTC = 2440587.5
    jd_total = 2440587.5 + ts_array / 86400.0
    jd_arr = np.floor(jd_total)
    fr_arr = jd_total - jd_arr

    arr = SatrecArray([satrec1, satrec2])
    err, r, _ = arr.sgp4(jd_arr, fr_arr)

    # Valid points where both satellites propagate without sgp4 error
    valid_mask = (err[0] == 0) & (err[1] == 0)
    diff = r[0] - r[1]
    distances = np.linalg.norm(diff, axis=-1)

    candidate_mask = valid_mask & (distances < threshold_distance_km)
    return np.where(candidate_mask)[0].tolist()


def cluster_candidate_steps(indices: List[int]) -> List[int]:
    """
    Groups contiguous step indices and returns representative local minimum indices for refinement.
    """
    if not indices:
        return []
    clusters: List[List[int]] = []
    curr = [indices[0]]

    for idx in indices[1:]:
        if idx == curr[-1] + 1:
            curr.append(idx)
        else:
            clusters.append(curr)
            curr = [idx]
    clusters.append(curr)

    return [c[len(c) // 2] for c in clusters]


def compute_state_vectors_at_timestamp(
    satrec1: Satrec,
    satrec2: Satrec,
    ts: float,
) -> Tuple[float, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Evaluates Euclidean distance and (r1, v1, r2, v2) state vectors at UTC timestamp ts.
    """
    jd_tot = 2440587.5 + ts / 86400.0
    jd = math.floor(jd_tot)
    fr = jd_tot - jd

    err1, r1, v1 = satrec1.sgp4(jd, fr)
    err2, r2, v2 = satrec2.sgp4(jd, fr)

    if err1 != 0 or err2 != 0:
        return float("inf"), np.zeros(3), np.zeros(3), np.zeros(3), np.zeros(3)

    r1_vec = np.array(r1, dtype=np.float64)
    v1_vec = np.array(v1, dtype=np.float64)
    r2_vec = np.array(r2, dtype=np.float64)
    v2_vec = np.array(v2, dtype=np.float64)

    dist = float(np.linalg.norm(r1_vec - r2_vec))
    return dist, r1_vec, v1_vec, r2_vec, v2_vec


def refine_tca(
    satrec1: Satrec,
    satrec2: Satrec,
    step_ts: float,
    step_seconds: float = 60.0,
) -> Tuple[float, float, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Refines candidate encounter to exact Time of Closest Approach (TCA) using minimize_scalar.
    Returns (tca_ts, miss_distance_km, r1, v1, r2, v2).
    """
    t_min = step_ts - step_seconds
    t_max = step_ts + step_seconds

    def objective(t: float) -> float:
        d, _, _, _, _ = compute_state_vectors_at_timestamp(satrec1, satrec2, t)
        return d

    res = minimize_scalar(objective, bounds=(t_min, t_max), method="bounded", options={"xatol": 1e-4})
    best_tca = float(res.x)
    miss_dist, r1, v1, r2, v2 = compute_state_vectors_at_timestamp(satrec1, satrec2, best_tca)

    center_dist, cr1, cv1, cr2, cv2 = compute_state_vectors_at_timestamp(satrec1, satrec2, step_ts)
    if center_dist < miss_dist:
        return step_ts, center_dist, cr1, cv1, cr2, cv2

    return best_tca, miss_dist, r1, v1, r2, v2


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
    t_hat = t_hat / np.linalg.norm(t_hat)

    delta_r = r2 - r1
    delta_v = v2 - v1

    miss_r = abs(float(np.dot(delta_r, r_hat)))
    miss_t = abs(float(np.dot(delta_r, t_hat)))
    miss_n = abs(float(np.dot(delta_r, n_hat)))

    total_miss = float(np.linalg.norm(delta_r))
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
    sigma_t = base_t * (1.0 + 0.60 * (age_days ** 1.2))
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


DATA_QUALITY_NOTE = (
    "Estimated covariance: TLE does not include precision radar covariance. "
    "Position sigma modeled with time-dependent along-track, radial, and cross-track dispersion."
)


def screen_all_watchlist_pairs(
    db: Session,
    start_dt: Optional[datetime] = None,
    duration_days: float = 7.0,
    hard_body_radius_m: float = 10.0,
) -> List[ConjunctionModel]:
    """
    Executes orbital screening between watchlist primary satellites and the full space object catalog.
    Persists detected conjunctions in the database and returns the list of ConjunctionModel objects.
    """
    if start_dt is None:
        start_dt = datetime.now(timezone.utc)

    start_ms = int(start_dt.timestamp() * 1000)
    end_dt = start_dt + timedelta(days=duration_days)
    end_ms = int(end_dt.timestamp() * 1000)

    # Fetch watchlist primary objects
    watchlist_stmt = select(SatelliteModel).where(SatelliteModel.is_watchlist == True)  # noqa: E712
    primary_satellites = db.scalars(watchlist_stmt).all()

    # Fetch all tracked satellites & debris
    all_sat_stmt = select(SatelliteModel)
    all_satellites = db.scalars(all_sat_stmt).all()

    conjunction_results: List[ConjunctionModel] = []
    seen_ids: set[str] = set()

    for primary in primary_satellites:
        satrec_p = Satrec.twoline2rv(primary.tle_line1.strip(), primary.tle_line2.strip())

        for secondary in all_satellites:
            if secondary.id == primary.id:
                continue

            # 1. Coarse altitude range filter (20 km buffer)
            if not check_altitude_overlap(
                primary.perigee_km, primary.apogee_km,
                secondary.perigee_km, secondary.apogee_km,
                buffer_km=20.0,
            ):
                continue

            # 2. Coarse search with SatrecArray (60s step, < 50 km)
            satrec_s = Satrec.twoline2rv(secondary.tle_line1.strip(), secondary.tle_line2.strip())
            candidate_steps = coarse_search_candidates(
                satrec_p, satrec_s,
                start_dt=start_dt,
                duration_days=duration_days,
                step_seconds=60.0,
                threshold_distance_km=50.0,
            )

            if not candidate_steps:
                continue

            # 3. Refine candidate clusters using minimize_scalar
            clusters = cluster_candidate_steps(candidate_steps)
            start_ts = start_dt.timestamp()

            for step_idx in clusters:
                approx_ts = start_ts + step_idx * 60.0
                tca_ts, miss_dist_km, r1, v1, r2, v2 = refine_tca(
                    satrec_p, satrec_s, approx_ts, step_seconds=60.0
                )

                if miss_dist_km > 50.0:
                    continue

                # 4. RTN Decomposition and Dual Pc Risk Evaluation
                from services.risk import evaluate_conjunction_risk

                tca_dt = datetime.fromtimestamp(tca_ts, tz=timezone.utc)
                risk_data = evaluate_conjunction_risk(
                    primary_sat=primary,
                    secondary_sat=secondary,
                    tca_dt=tca_dt,
                    r1=r1,
                    v1=v1,
                    r2=r2,
                    v2=v2,
                    weather=None,
                    hard_body_radius_m=hard_body_radius_m,
                )

                miss_r = risk_data["radial_miss_km"]
                miss_t = risk_data["in_track_miss_km"]
                miss_n = risk_data["cross_track_miss_km"]
                total_miss = risk_data["miss_distance_km"]
                rel_vel = risk_data["relative_velocity_km_s"]
                pc_raw = risk_data["pc_raw"]
                pc_ml = risk_data["pc_ml"]
                pc_ml_calibrated = risk_data["pc_ml_calibrated"]
                risk_lvl = risk_data["risk_level"]
                rec_action = risk_data["recommended_action"]
                cov1 = risk_data["primary_covariance_rtn_m"]
                cov2 = risk_data["secondary_covariance_rtn_m"]
                ml_avail = risk_data["ml_available"]
                mod_ver = risk_data["model_version"]

                # Stable, deterministic ID from pair NORAD IDs and rounded TCA minute
                tca_ts_rounded = round(tca_ts / 60.0) * 60.0
                tca_dt_rounded = datetime.fromtimestamp(tca_ts_rounded, tz=timezone.utc)
                base_id = f"CONJ-{primary.norad_id}-{secondary.norad_id}-{tca_dt_rounded.strftime('%Y%m%d%H%M')}"
                conj_id = base_id
                if conj_id in seen_ids:
                    suffix = 2
                    while f"{base_id}-{suffix}" in seen_ids:
                        suffix += 1
                    conj_id = f"{base_id}-{suffix}"
                seen_ids.add(conj_id)

                # 8. Compute recommended delta-V and fuel cost for CRITICAL events
                rec_dv_ms: Optional[float] = None
                rec_fuel_kg: Optional[float] = None

                if risk_lvl == "CRITICAL":
                    from services.maneuver import calculate_separation_gain_km, calculate_fuel_consumption_kg

                    for dv_step in np.arange(0.01, 2.001, 0.01):
                        dv_cand = round(float(dv_step), 2)
                        gain_km = calculate_separation_gain_km(
                            delta_v_ms=dv_cand,
                            direction="PROGRADE",
                            lead_time_hours=12.0,
                            altitude_km=primary.altitude_km,
                        )
                        post_r = miss_r
                        post_t = miss_t + gain_km
                        post_n = miss_n
                        post_miss_km = math.sqrt(post_r**2 + post_t**2 + post_n**2)
                        if post_miss_km >= 2.0:
                            rec_dv_ms = dv_cand
                            break

                    if rec_dv_ms is None:
                        rec_dv_ms = 2.0

                    rec_fuel_kg = round(
                        calculate_fuel_consumption_kg(
                            spacecraft_mass_kg=710.0,
                            isp_seconds=220.0,
                            delta_v_ms=rec_dv_ms,
                        ),
                        3,
                    )

                conjunction_obj = ConjunctionModel(
                    id=conj_id,
                    primary_sat_id=primary.id,
                    secondary_sat_id=secondary.id,
                    tca_utc=tca_dt.isoformat(),
                    tca_ms=int(tca_ts * 1000),
                    miss_distance_km=round(total_miss, 3),
                    radial_miss_km=round(miss_r, 3),
                    in_track_miss_km=round(miss_t, 3),
                    cross_track_miss_km=round(miss_n, 3),
                    relative_velocity_km_s=round(rel_vel, 2),
                    raw_probability=pc_raw,
                    calibrated_probability=pc_ml_calibrated,
                    risk_level=risk_lvl,
                    primary_radial_sigma_m=cov1[0],
                    primary_in_track_sigma_m=cov1[1],
                    primary_cross_track_sigma_m=cov1[2],
                    secondary_radial_sigma_m=cov2[0],
                    secondary_in_track_sigma_m=cov2[1],
                    secondary_cross_track_sigma_m=cov2[2],
                    recommended_action=rec_action,
                    recommended_delta_v_ms=rec_dv_ms,
                    maneuver_fuel_cost_kg=rec_fuel_kg,
                    data_freshness_utc=datetime.now(timezone.utc).isoformat(),
                    data_quality_note=DATA_QUALITY_NOTE,
                    pc_raw=pc_raw,
                    pc_ml=pc_ml,
                    pc_ml_calibrated=pc_ml_calibrated,
                    ml_available=ml_avail,
                    model_version=mod_ver,
                    data_source="real",
                )
                conjunction_results.append(conjunction_obj)

    # In one transaction: delete past conjunctions, replace window rows for screened pairs, and add newly found conjunctions
    primary_ids = [primary.id for primary in primary_satellites]
    try:
        # Delete conjunctions whose TCA is in the past
        db.execute(delete(ConjunctionModel).where(ConjunctionModel.tca_ms < start_ms))

        # Replace rows for the same primary satellites that fall inside the new screening window
        if primary_ids:
            db.execute(
                delete(ConjunctionModel).where(
                    ConjunctionModel.primary_sat_id.in_(primary_ids),
                    ConjunctionModel.tca_ms >= start_ms,
                    ConjunctionModel.tca_ms <= end_ms,
                )
            )

        for conj in conjunction_results:
            db.add(conj)

        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("Failed to commit screening conjunctions to database: %s", exc)
        raise

    logger.info("Orbital screening completed: %d conjunctions found.", len(conjunction_results))

    # Dispatch alerts for newly identified conjunctions exceeding alert thresholds
    if conjunction_results:
        try:
            try:
                from backend.services.notifier import process_screening_alerts
            except ImportError:
                from services.notifier import process_screening_alerts
            process_screening_alerts(db, conjunction_results)
        except Exception as exc:
            logger.error("Failed to process screening alerts: %s", exc)

    return conjunction_results

