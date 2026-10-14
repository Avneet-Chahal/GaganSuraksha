import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.orm import Session
from sqlalchemy import select
from backend.database import get_db, SessionLocal
from backend.models.db_models import ConjunctionModel
from backend.schemas.types import (
    ConjunctionEvent,
    SatelliteRecord,
    CovarianceMatrix,
)
from backend.services.screening import screen_all_watchlist_pairs

logger = logging.getLogger("gagan_suraksha.screening")
router = APIRouter(prefix="/conjunctions", tags=["Conjunctions"])


def run_screening_task() -> int:
    logger.info("Executing background conjunction screening task...")
    db = SessionLocal()
    try:
        results = screen_all_watchlist_pairs(db)
        logger.info("Background screening task completed: %d conjunctions found.", len(results))
        return len(results)
    except Exception as exc:
        logger.error("Error during background conjunction screening task: %s", exc, exc_info=True)
        return 0
    finally:
        db.close()


def to_conjunction_event(c: ConjunctionModel) -> ConjunctionEvent:
    """Converts a database ConjunctionModel to a Pydantic ConjunctionEvent."""
    return ConjunctionEvent(
        id=c.id,
        primary_sat=SatelliteRecord.model_validate(c.primary_sat),
        secondary_sat=SatelliteRecord.model_validate(c.secondary_sat),
        tca_utc=c.tca_utc,
        tca_ms=c.tca_ms,
        miss_distance_km=c.miss_distance_km,
        radial_miss_km=c.radial_miss_km,
        in_track_miss_km=c.in_track_miss_km,
        cross_track_miss_km=c.cross_track_miss_km,
        relative_velocity_km_s=c.relative_velocity_km_s,
        raw_probability=c.raw_probability,
        calibrated_probability=c.calibrated_probability,
        risk_level=c.risk_level,  # type: ignore[arg-type]
        primary_covariance=CovarianceMatrix(
            radial_sigma_m=c.primary_radial_sigma_m,
            in_track_sigma_m=c.primary_in_track_sigma_m,
            cross_track_sigma_m=c.primary_cross_track_sigma_m,
        ),
        secondary_covariance=CovarianceMatrix(
            radial_sigma_m=c.secondary_radial_sigma_m,
            in_track_sigma_m=c.secondary_in_track_sigma_m,
            cross_track_sigma_m=c.secondary_cross_track_sigma_m,
        ),
        recommended_action=c.recommended_action,  # type: ignore[arg-type]
        recommended_delta_v_ms=c.recommended_delta_v_ms,
        maneuver_fuel_cost_kg=c.maneuver_fuel_cost_kg,
        data_freshness_utc=c.data_freshness_utc,
        data_quality_note=c.data_quality_note,
        pc_raw=c.pc_raw if getattr(c, "pc_raw", None) is not None else c.raw_probability,
        pc_ml=c.pc_ml if getattr(c, "pc_ml", None) is not None else c.calibrated_probability,
        pc_ml_calibrated=c.pc_ml_calibrated if getattr(c, "pc_ml_calibrated", None) is not None else c.calibrated_probability,
        ml_available=getattr(c, "ml_available", True),
        model_version=getattr(c, "model_version", "v1.0.0"),
        covariance={
            "primary": {
                "radialM": c.primary_radial_sigma_m,
                "inTrackM": c.primary_in_track_sigma_m,
                "crossTrackM": c.primary_cross_track_sigma_m,
            },
            "secondary": {
                "radialM": c.secondary_radial_sigma_m,
                "inTrackM": c.secondary_in_track_sigma_m,
                "crossTrackM": c.secondary_cross_track_sigma_m,
            },
        },
        data_source=getattr(c, "data_source", "real"),
    )


@router.get("", response_model=List[ConjunctionEvent])
def get_conjunctions(
    risk: Optional[str] = Query(None, description="Filter by risk level: CRITICAL, WARNING, or NOMINAL"),
    db: Session = Depends(get_db),
) -> List[ConjunctionEvent]:
    """Retrieves all predicted close-approach conjunction events, optionally filtered by risk level."""
    stmt = select(ConjunctionModel)
    if risk:
        stmt = stmt.where(ConjunctionModel.risk_level == risk.upper())
    stmt = stmt.order_by(ConjunctionModel.tca_ms.asc())
    conjunctions = db.scalars(stmt).all()
    return [to_conjunction_event(c) for c in conjunctions]


@router.get("/{id}", response_model=ConjunctionEvent)
def get_conjunction_by_id(
    id: str,
    db: Session = Depends(get_db),
) -> ConjunctionEvent:
    """Retrieves a single conjunction event by its unique ID."""
    stmt = select(ConjunctionModel).where(ConjunctionModel.id == id)
    conjunction = db.scalars(stmt).first()
    if not conjunction:
        raise HTTPException(status_code=404, detail=f"Conjunction event '{id}' not found.")
    return to_conjunction_event(conjunction)


@router.post("/screen", status_code=202)
def trigger_screening_job(
    background_tasks: BackgroundTasks,
    wait: bool = Query(False, description="If true, execute screening synchronously and return count."),
    db: Session = Depends(get_db),
) -> dict:
    """Triggers conjunction screening for all watchlist satellites. Can run in background or synchronously with ?wait=true."""
    if wait:
        logger.info("Triggering synchronous conjunction screening via POST /conjunctions/screen?wait=true...")
        results = screen_all_watchlist_pairs(db)
        logger.info("Synchronous screening completed: %d conjunctions found.", len(results))
        return {
            "status": "COMPLETED",
            "message": f"Conjunction screening completed: found {len(results)} conjunctions.",
            "conjunctionsCount": len(results),
        }

    background_tasks.add_task(run_screening_task)
    return {"status": "QUEUED", "message": "Conjunction screening background job started."}
