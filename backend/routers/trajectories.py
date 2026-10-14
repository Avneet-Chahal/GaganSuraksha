from typing import List
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from backend.database import get_db
from backend.models.db_models import SatelliteModel
from backend.schemas.types import TrajectoryResponse
from backend.services.sgp4_service import (
    generate_trajectory_samples,
    parse_iso_datetime,
)

router = APIRouter(prefix="/trajectories", tags=["Trajectories"])

MAX_SATELLITE_IDS = 20
MAX_WINDOW_DAYS = 7
MAX_WINDOW_SECONDS = MAX_WINDOW_DAYS * 86400  # 604,800 seconds
MAX_POINTS_PER_OBJECT = 5000


@router.get("", response_model=List[TrajectoryResponse])
def get_trajectories(
    ids: str = Query(..., description="Comma-separated satellite/debris catalog IDs"),
    start: str = Query(..., description="Start window UTC ISO 8601 string"),
    end: str = Query(..., description="End window UTC ISO 8601 string"),
    step: int = Query(120, description="Step seconds between trajectory points (default: 120)"),
    corrected: bool = Query(False, description="Apply ML error-correction to positions"),
    db: Session = Depends(get_db),
) -> List[TrajectoryResponse]:
    """
    Generates time-series ECI (TEME) trajectory positions and velocities using SGP4 propagation.

    Constraints & Validation:
    - At most 20 IDs allowed per request (HTTP 422 if exceeded)
    - At most 7 days time window allowed (HTTP 422 if exceeded)
    - At most 5,000 trajectory points per object allowed (HTTP 422 if exceeded)
    - Step must be greater than 0 seconds (HTTP 422 if invalid)
    - Unknown/missing satellite IDs return HTTP 404 listing the missing IDs
    - Skips points where SGP4 propagation returns an error code
    """
    # 1. Parse and validate IDs list
    raw_ids = [id_str.strip() for id_str in ids.split(",") if id_str.strip()]
    if not raw_ids:
        raise HTTPException(
            status_code=422,
            detail="At least one satellite ID must be provided in 'ids' query parameter.",
        )

    # Deduplicate while preserving user request order
    seen = set()
    unique_ids: List[str] = []
    for sat_id in raw_ids:
        if sat_id not in seen:
            seen.add(sat_id)
            unique_ids.append(sat_id)

    if len(unique_ids) > MAX_SATELLITE_IDS:
        raise HTTPException(
            status_code=422,
            detail=f"Maximum of {MAX_SATELLITE_IDS} satellite IDs allowed per request. Received {len(unique_ids)} IDs.",
        )

    # 2. Validate start and end timestamps
    try:
        start_dt = parse_iso_datetime(start)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid ISO UTC timestamp for 'start': '{start}'. Expected ISO 8601 format (e.g. 2026-10-10T12:00:00Z).",
        ) from exc

    try:
        end_dt = parse_iso_datetime(end)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid ISO UTC timestamp for 'end': '{end}'. Expected ISO 8601 format (e.g. 2026-10-10T13:00:00Z).",
        ) from exc

    start_ts = start_dt.timestamp()
    end_ts = end_dt.timestamp()

    if end_ts < start_ts:
        raise HTTPException(
            status_code=422,
            detail=f"End time ('{end}') must be greater than or equal to start time ('{start}').",
        )

    duration_seconds = end_ts - start_ts
    if duration_seconds > MAX_WINDOW_SECONDS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Time window cannot exceed {MAX_WINDOW_DAYS} days ({MAX_WINDOW_SECONDS:,} seconds). "
                f"Requested duration is {duration_seconds:,.1f} seconds."
            ),
        )

    # 3. Validate step and point density limit
    if step <= 0:
        raise HTTPException(
            status_code=422,
            detail=f"Step interval must be greater than 0 seconds. Received step={step}.",
        )

    estimated_points = int(duration_seconds // step) + 1
    if estimated_points > MAX_POINTS_PER_OBJECT:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Trajectory calculation exceeds maximum limit of {MAX_POINTS_PER_OBJECT:,} points per object "
                f"(requested parameters yield {estimated_points:,} points). "
                f"Please increase step interval or reduce time window."
            ),
        )

    # 4. Check for unknown IDs against the catalog
    stmt = select(SatelliteModel).where(SatelliteModel.id.in_(unique_ids))
    satellites = db.scalars(stmt).all()
    sat_map = {sat.id: sat for sat in satellites}

    missing_ids = [sat_id for sat_id in unique_ids if sat_id not in sat_map]
    if missing_ids:
        raise HTTPException(
            status_code=404,
            detail=f"Satellite IDs not found: {', '.join(missing_ids)}",
        )

    # 5. Compute SGP4 trajectory points
    responses: List[TrajectoryResponse] = []
    for sat_id in unique_ids:
        sat = sat_map[sat_id]
        trajectory = generate_trajectory_samples(
            satellite_id=sat.id,
            line1=sat.tle_line1,
            line2=sat.tle_line2,
            start_time_iso=start,
            end_time_iso=end,
            step_seconds=step,
            start_dt=start_dt,
            end_dt=end_dt,
        )
        responses.append(trajectory)

    # 6. Apply ML error-correction to positions if requested
    if corrected:
        try:
            import numpy as np
            from datetime import datetime, timezone
            from backend.schemas.types import TrajectoryPoint
            from backend.app.ml.predict import correct_state, StatePredictor

            predictor = StatePredictor.get_instance()
            if predictor.ml_available:
                for resp in responses:
                    sat = sat_map.get(resp.satellite_id)
                    tle_epoch = sat.tle_epoch if sat else start_dt
                    corrected_points: List[TrajectoryPoint] = []
                    for pt in resp.points:
                        pt_dt = datetime.fromtimestamp(pt.time_ms / 1000.0, tz=timezone.utc)
                        r_vec = np.array([pt.x, pt.y, pt.z], dtype=np.float64)
                        v_vec = np.array([pt.vx or 0.0, pt.vy or 0.0, pt.vz or 0.0], dtype=np.float64)
                        corr = correct_state(
                            sat_state=(r_vec, v_vec),
                            tle_epoch=tle_epoch,
                            t_target=pt_dt,
                            predictor=predictor,
                        )
                        c_pos = corr.corrected_position
                        corrected_points.append(
                            TrajectoryPoint(
                                time_ms=pt.time_ms,
                                x=round(float(c_pos[0]), 3),
                                y=round(float(c_pos[1]), 3),
                                z=round(float(c_pos[2]), 3),
                                vx=pt.vx,
                                vy=pt.vy,
                                vz=pt.vz,
                            )
                        )
                    resp.points = corrected_points
        except Exception:
            pass

    return responses
