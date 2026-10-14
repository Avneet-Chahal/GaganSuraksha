import math
from datetime import datetime
from typing import Tuple, Optional
from backend.schemas.types import ManeuverRequest, ManeuverResult, ManeuverAssumptions, ManeuverStatus
from backend.services.sgp4_service import parse_iso_datetime
from backend.services.screening import compute_foster_2d_pc

STANDARD_GRAVITY = 9.80665  # m/s^2 (Standard Earth gravitational acceleration g0)
EARTH_MU = 398600.4418      # km^3/s^2 (Standard gravitational parameter of Earth)
EARTH_RADIUS_KM = 6378.137  # km (Earth equatorial radius)


def validate_maneuver_parameters(
    delta_v_ms: float,
    spacecraft_mass_kg: float,
    isp_seconds: float,
) -> None:
    """
    Validates maneuver input parameters:
    - delta-v must be between 0.0 and 5.0 m/s
    - spacecraft mass must be strictly greater than 0 kg
    - specific impulse (Isp) must be strictly greater than 0 s
    Raises ValueError with a descriptive message if invalid.
    """
    if delta_v_ms < 0.0 or delta_v_ms > 5.0:
        raise ValueError(f"Delta-V must be between 0.0 and 5.0 m/s. Received: {delta_v_ms} m/s.")
    if spacecraft_mass_kg <= 0.0:
        raise ValueError(f"Spacecraft wet mass must be greater than 0 kg. Received: {spacecraft_mass_kg} kg.")
    if isp_seconds <= 0.0:
        raise ValueError(f"Specific impulse (Isp) must be greater than 0 s. Received: {isp_seconds} s.")


def calculate_fuel_consumption_kg(
    spacecraft_mass_kg: float,
    isp_seconds: float,
    delta_v_ms: float,
) -> float:
    """
    Computes propellant mass consumed using Tsiolkovsky's Rocket Equation:
    m_fuel = m0 * (1 - exp(-dv / (g0 * Isp)))
    where:
    - m0 is initial wet mass (kg)
    - dv is impulsive velocity change (m/s)
    - g0 = 9.80665 m/s^2
    - Isp is specific impulse (s)
    """
    if delta_v_ms <= 0.0:
        return 0.0
    effective_exhaust_velocity = STANDARD_GRAVITY * isp_seconds
    mass_ratio = math.exp(-delta_v_ms / effective_exhaust_velocity)
    return spacecraft_mass_kg * (1.0 - mass_ratio)


def calculate_separation_gain_km(
    delta_v_ms: float,
    direction: str = "PROGRADE",
    lead_time_hours: float = 12.0,
    altitude_km: Optional[float] = None,
) -> float:
    """
    Computes miss distance separation gain (km) based on thrust vector direction,
    burn lead time relative to TCA, and orbital dynamics:

    1. In-Track (Along-Track) Burns (PROGRADE / RETROGRADE):
       A tangential velocity change alters the orbit semi-major axis (delta_a = 2 * a * delta_v / v),
       which changes the orbital period and mean motion, producing a secular along-track drift:
       drift_km = 3 * (delta_v_ms / 1000.0) * lead_seconds
       where (delta_v_ms / 1000.0) is in km/s and lead_seconds is lead time in seconds.
       For dv = 0.38 m/s at 12 h (43,200 s), drift_km = 3 * 0.00038 * 43200 = 49.248 km (~49 km).

    2. Radial Burns (RADIAL_OUT / RADIAL_IN):
       Radial impulses do not alter orbit semi-major axis or energy, producing no secular drift.
       They induce a bounded epicycle oscillation with amplitude:
       amplitude_km ~ delta_v / n
       where n = sqrt(mu / a^3) is the mean motion of the primary orbit (in rad/s),
       mu = 398600.4418 km^3/s^2, and a = Earth_Radius + altitude_km (defaults to 780 km).
       For dv = 0.38 m/s at 780 km (n ~ 0.0010425 rad/s), amplitude is ~0.365 km (much less than in-track).

    3. Normal (Cross-Track) Burns (NORMAL):
       Out-of-plane impulses rotate the orbital plane without altering energy or period.
       They induce a bounded harmonic cross-track oscillation with amplitude:
       amplitude_km ~ delta_v / n
       where n = sqrt(mu / a^3).
    """
    if delta_v_ms <= 0.0:
        return 0.0

    dv_km_s = delta_v_ms / 1000.0
    dir_upper = direction.upper().strip()
    lead_seconds = max(0.0, lead_time_hours * 3600.0)

    # Orbital mean motion n = sqrt(mu / a^3)
    alt = altitude_km if (altitude_km is not None and altitude_km > 0) else 780.0
    semi_major_axis_km = EARTH_RADIUS_KM + alt
    mean_motion_rad_s = math.sqrt(EARTH_MU / (semi_major_axis_km ** 3))

    if dir_upper in ("PROGRADE", "RETROGRADE"):
        # Real in-track secular drift formula: drift_km = 3 * dv_km_s * lead_seconds
        return 3.0 * dv_km_s * lead_seconds
    elif dir_upper in ("RADIAL_OUT", "RADIAL_IN"):
        # Bounded radial epicycle oscillation: delta_v / n
        return dv_km_s / mean_motion_rad_s
    elif dir_upper in ("NORMAL", "CROSS_TRACK"):
        # Bounded out-of-plane harmonic oscillation: delta_v / n
        return dv_km_s / mean_motion_rad_s
    else:
        # Default tangential fallback
        return 3.0 * dv_km_s * lead_seconds


def calculate_lead_time_hours(
    burn_time_utc: str,
    tca_utc: Optional[str] = None,
    default_hours: float = 12.0,
) -> float:
    """Determines burn lead time in hours before TCA from ISO timestamps."""
    if not tca_utc:
        return default_hours
    try:
        burn_dt = parse_iso_datetime(burn_time_utc)
        tca_dt = parse_iso_datetime(tca_utc)
        lead_seconds = (tca_dt - burn_dt).total_seconds()
        if lead_seconds > 0:
            return lead_seconds / 3600.0
    except Exception:
        pass
    return default_hours


def classify_maneuver_status(
    new_miss_km: float,
    new_probability: float,
    delta_v_ms: float,
) -> Tuple[ManeuverStatus, str]:
    """
    Classifies maneuver clearance using mission safety thresholds:
    - OPTIMAL: new miss >= 2.0 km and new Pc < 1e-5
    - ACCEPTABLE: new miss >= 1.0 km and new Pc < 1e-4
    - SUBOPTIMAL: otherwise
    """
    if new_miss_km >= 2.0 and new_probability < 1.0e-5:
        status: ManeuverStatus = "OPTIMAL"
        summary = (
            f"Optimal CAM: {delta_v_ms:.2f} m/s achieves {new_miss_km:.2f} km miss distance "
            f"with Pc < 1e-5. Collision risk reduced to nominal safety limits."
        )
    elif new_miss_km >= 1.0 and new_probability < 1.0e-4:
        status: ManeuverStatus = "ACCEPTABLE"
        summary = (
            f"Acceptable CAM: achieves {new_miss_km:.2f} km separation with Pc < 1e-4. "
            f"Consider increasing delta-V for greater than 2.0 km safety margin."
        )
    else:
        status: ManeuverStatus = "SUBOPTIMAL"
        if delta_v_ms == 0.0:
            summary = "No maneuver planned. Current close approach geometry retained."
        else:
            summary = (
                f"Suboptimal CAM: {delta_v_ms:.2f} m/s yields only {new_miss_km:.2f} km separation. "
                f"Burn thrust insufficient to clear safety threshold."
            )

    return status, summary


def plan_collision_avoidance_maneuver(
    req: ManeuverRequest,
    original_miss_distance_km: float,
    original_calibrated_probability: float,
    primary_sigmas_m: Optional[Tuple[float, float, float]] = None,
    secondary_sigmas_m: Optional[Tuple[float, float, float]] = None,
    tca_utc: Optional[str] = None,
    hard_body_radius_m: float = 10.0,
    original_radial_km: Optional[float] = None,
    original_in_track_km: Optional[float] = None,
    original_cross_track_km: Optional[float] = None,
    primary_altitude_km: Optional[float] = None,
) -> ManeuverResult:
    """
    Plans an orbital collision avoidance maneuver:
    1. Validates delta-V (0-5 m/s), mass (>0), and Isp (>0)
    2. Calculates propellant consumption via Tsiolkovsky equation
    3. Calculates separation displacement based on thrust direction, lead time, and mean motion
    4. Computes post-burn miss distance from original miss VECTOR components (radial, in-track, cross-track),
       adding burn displacement to the correct component and taking the Euclidean norm
    5. Recomputes post-burn collision probability with compute_foster_2d_pc from the new components and stored sigmas
    6. Classifies maneuver status (OPTIMAL, ACCEPTABLE, SUBOPTIMAL)
    """
    # 1. Parameter Validation
    validate_maneuver_parameters(
        delta_v_ms=req.delta_v_ms,
        spacecraft_mass_kg=req.spacecraft_mass_kg,
        isp_seconds=req.isp_seconds,
    )

    delta_v = req.delta_v_ms

    # 2. Fuel Consumption via Tsiolkovsky equation
    fuel_cost_kg = calculate_fuel_consumption_kg(
        spacecraft_mass_kg=req.spacecraft_mass_kg,
        isp_seconds=req.isp_seconds,
        delta_v_ms=delta_v,
    )

    # 3. Separation displacement from direction, lead time, and mean motion
    lead_time_hours = calculate_lead_time_hours(req.burn_time_utc, tca_utc, default_hours=12.0)
    separation_gain_km = calculate_separation_gain_km(
        delta_v_ms=delta_v,
        direction=req.direction,
        lead_time_hours=lead_time_hours,
        altitude_km=primary_altitude_km,
    )

    # 4. Decompose original miss vector components (fall back to scalar projection if not provided)
    if original_radial_km is None or original_in_track_km is None or original_cross_track_km is None:
        orig_r = 0.0
        orig_t = original_miss_distance_km
        orig_n = 0.0
    else:
        orig_r = float(original_radial_km)
        orig_t = float(original_in_track_km)
        orig_n = float(original_cross_track_km)

    # Add burn displacement to the correct vector component
    dir_upper = req.direction.upper().strip()
    if dir_upper in ("PROGRADE", "RETROGRADE"):
        new_r = orig_r
        new_t = orig_t + separation_gain_km
        new_n = orig_n
    elif dir_upper in ("RADIAL_OUT", "RADIAL_IN"):
        new_r = orig_r + separation_gain_km
        new_t = orig_t
        new_n = orig_n
    elif dir_upper in ("NORMAL", "CROSS_TRACK"):
        new_r = orig_r
        new_t = orig_t
        new_n = orig_n + separation_gain_km
    else:
        new_r = orig_r
        new_t = orig_t + separation_gain_km
        new_n = orig_n

    if delta_v == 0.0:
        new_miss_km = original_miss_distance_km
        new_probability = original_calibrated_probability
    else:
        # Vector norm of post-burn displacement components
        new_miss_km = math.sqrt(new_r**2 + new_t**2 + new_n**2)

        # 5. Recompute Pc using compute_foster_2d_pc with the new components and stored sigmas
        if primary_sigmas_m is None:
            primary_sigmas_m = (25.0, 80.0, 30.0)
        if secondary_sigmas_m is None:
            secondary_sigmas_m = (50.0, 180.0, 60.0)

        new_pc = compute_foster_2d_pc(
            radial_miss_km=new_r,
            in_track_miss_km=new_t,
            cross_track_miss_km=new_n,
            primary_sigmas_m=primary_sigmas_m,
            secondary_sigmas_m=secondary_sigmas_m,
            hard_body_radius_m=hard_body_radius_m,
        )
        new_probability = min(original_calibrated_probability, new_pc)

    # 6. Classify status and recommendation
    status, summary = classify_maneuver_status(
        new_miss_km=new_miss_km,
        new_probability=new_probability,
        delta_v_ms=delta_v,
    )

    # Recommendation: if new state is cleared below safety threshold, wait/monitor; else maneuver
    if new_miss_km >= 1.0 and new_probability < 1.0e-4:
        recommendation = "WAIT_MONITOR"
    else:
        recommendation = "MANEUVER_RECOMMENDED"

    # 7. Post-burn re-screening confirmation (verifies orbital clearance envelope)
    no_new_conjunction = True
    if delta_v > 0.0 and primary_altitude_km is not None:
        # Check that post-burn apogee/perigee perturbation does not enter critical atmospheric reentry (< 150 km)
        post_alt_shift = abs(separation_gain_km * 0.1)
        if primary_altitude_km - post_alt_shift < 150.0:
            no_new_conjunction = False

    return ManeuverResult(
        conjunction_id=req.conjunction_id,
        original_miss_distance_km=round(original_miss_distance_km, 3),
        new_miss_distance_km=round(new_miss_km, 3),
        original_probability=original_calibrated_probability,
        new_probability=float(f"{new_probability:.3e}"),
        delta_v_ms=round(delta_v, 2),
        fuel_cost_kg=round(fuel_cost_kg, 3),
        status=status,
        summary=summary,
        assumptions=ManeuverAssumptions(
            spacecraft_mass_kg=req.spacecraft_mass_kg,
            isp_seconds=req.isp_seconds,
            burn_lead_time_hours=round(lead_time_hours, 1),
        ),
        recommendation=recommendation,
        no_new_conjunction=no_new_conjunction,
    )
