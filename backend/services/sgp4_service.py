import math
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from sgp4.api import Satrec, jday
from backend.schemas.types import TrajectoryPoint, TrajectoryResponse

EARTH_RADIUS_KM = 6371.0


def parse_iso_datetime(dt_str: str) -> datetime:
    """Parses an ISO 8601 string to a timezone-aware UTC datetime."""
    clean_str = dt_str.replace("Z", "+00:00")
    dt = datetime.fromisoformat(clean_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def propagate_single_point(
    satrec: Satrec,
    dt: datetime,
) -> Optional[Tuple[float, float, float, float, float, float]]:
    """
    Propagates a Satrec object at the given datetime.
    Returns (x, y, z, vx, vy, vz) in km and km/s (ECI/TEME), or None if error.
    """
    try:
        jd, fr = jday(
            dt.year,
            dt.month,
            dt.day,
            dt.hour,
            dt.minute,
            dt.second + dt.microsecond * 1e-6,
        )
        error_code, r, v = satrec.sgp4(jd, fr)
        if error_code != 0:
            return None
        return r[0], r[1], r[2], v[0], v[1], v[2]
    except Exception:
        return None


def generate_trajectory_samples(
    satellite_id: str,
    line1: str,
    line2: str,
    start_time_iso: str,
    end_time_iso: str,
    step_seconds: int = 120,
    start_dt: Optional[datetime] = None,
    end_dt: Optional[datetime] = None,
) -> TrajectoryResponse:
    """
    Generates time-series ECI (TEME) trajectory points between start_time and end_time
    using the standard SGP4 orbital propagator.
    """
    if start_dt is None:
        start_dt = parse_iso_datetime(start_time_iso)
    if end_dt is None:
        end_dt = parse_iso_datetime(end_time_iso)

    start_ts = start_dt.timestamp()
    end_ts = end_dt.timestamp()

    if end_ts < start_ts:
        end_ts = start_ts + 3600  # Default 1 hour fallback window

    step = max(1, step_seconds)  # Ensure positive step
    satrec = Satrec.twoline2rv(line1.strip(), line2.strip())

    points: List[TrajectoryPoint] = []
    current_ts = start_ts

    while current_ts <= end_ts:
        dt = datetime.fromtimestamp(current_ts, tz=timezone.utc)
        result = propagate_single_point(satrec, dt)
        if result is not None:
            x, y, z, vx, vy, vz = result
            points.append(
                TrajectoryPoint(
                    time_ms=int(current_ts * 1000),
                    x=round(x, 3),
                    y=round(y, 3),
                    z=round(z, 3),
                    vx=round(vx, 4),
                    vy=round(vy, 4),
                    vz=round(vz, 4),
                )
            )
        current_ts += step

    return TrajectoryResponse(
        satellite_id=satellite_id,
        step_seconds=step,
        start_time=start_time_iso,
        end_time=end_time_iso,
        points=points,
    )
