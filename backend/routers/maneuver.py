from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from backend.database import get_db
from backend.models.db_models import ConjunctionModel
from backend.schemas.types import ManeuverRequest, ManeuverResult
from backend.services.maneuver_service import plan_collision_avoidance_maneuver

router = APIRouter(prefix="/maneuver", tags=["Maneuver"])


@router.post("", response_model=ManeuverResult)
def post_plan_maneuver(
    req: ManeuverRequest,
    db: Session = Depends(get_db),
) -> ManeuverResult:
    """
    Computes delta-V requirements, propellant mass consumption (Tsiolkovsky equation),
    post-burn miss distance, and calibrated collision probability for an avoidance maneuver.
    """
    stmt = select(ConjunctionModel).where(ConjunctionModel.id == req.conjunction_id)
    conjunction = db.scalars(stmt).first()

    if not conjunction:
        raise HTTPException(status_code=404, detail=f"Conjunction event '{req.conjunction_id}' not found.")

    orig_miss = conjunction.miss_distance_km
    orig_pc = conjunction.pc_ml_calibrated if getattr(conjunction, "pc_ml_calibrated", None) is not None else conjunction.calibrated_probability
    tca_utc = conjunction.tca_utc
    primary_sigmas = (
        conjunction.primary_radial_sigma_m,
        conjunction.primary_in_track_sigma_m,
        conjunction.primary_cross_track_sigma_m,
    )
    secondary_sigmas = (
        conjunction.secondary_radial_sigma_m,
        conjunction.secondary_in_track_sigma_m,
        conjunction.secondary_cross_track_sigma_m,
    )
    primary_alt = conjunction.primary_sat.altitude_km if conjunction.primary_sat else 780.0

    try:
        return plan_collision_avoidance_maneuver(
            req=req,
            original_miss_distance_km=orig_miss,
            original_calibrated_probability=orig_pc,
            primary_sigmas_m=primary_sigmas,
            secondary_sigmas_m=secondary_sigmas,
            tca_utc=tca_utc,
            original_radial_km=conjunction.radial_miss_km,
            original_in_track_km=conjunction.in_track_miss_km,
            original_cross_track_km=conjunction.cross_track_miss_km,
            primary_altitude_km=primary_alt,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

