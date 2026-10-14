from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from backend.database import get_db
from backend.models.db_models import SatelliteModel, IngestionStatusModel
from backend.schemas.types import DataSourceStatus

router = APIRouter(prefix="/sources", tags=["Sources"])


@router.get("", response_model=List[DataSourceStatus])
def get_sources(
    db: Session = Depends(get_db),
) -> List[DataSourceStatus]:
    """
    Reports honest, real operational status for:
    1. CelesTrak TLE Ingestion: Read from ingestion_status table.
       Returns DEGRADED or STANDBY if last fetch failed or data is synthetic (never ONLINE).
    2. SGP4 Orbit Propagator: In-process analytical propagator.
    Does not invent sources that do not exist.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    total_records = db.scalars(select(func.count(SatelliteModel.id))).first() or 0
    celestrak_records = (
        db.scalars(
            select(func.count(SatelliteModel.id)).where(SatelliteModel.data_source == "CELESTRAK")
        ).first()
        or 0
    )

    status_row = db.query(IngestionStatusModel).filter(IngestionStatusModel.id == 1).first()

    if status_row:
        last_updated = status_row.last_success_utc or status_row.last_fetch_utc or now_iso
        latency = int(round(status_row.latency_seconds))
        # Status determination:
        # If last fetch failed -> DEGRADED
        # If all data is synthetic (celestrak_records == 0) -> STANDBY or DEGRADED (never ONLINE)
        # Only ONLINE when last fetch succeeded AND real CelesTrak records are active
        if status_row.status == "DEGRADED" or status_row.error_message:
            celestrak_status = "DEGRADED"
        elif celestrak_records == 0:
            celestrak_status = "STANDBY"
        elif status_row.status == "ONLINE":
            celestrak_status = "ONLINE"
        else:
            celestrak_status = "STANDBY"

        record_count = celestrak_records if celestrak_records > 0 else status_row.record_count
    else:
        celestrak_status = "STANDBY"
        last_updated = now_iso
        latency = 0
        record_count = 0

    sources: List[DataSourceStatus] = [
        DataSourceStatus(
            name="CelesTrak TLE Ingestion",
            source="CelesTrak GP Element Sets / 18th SDS",
            status=celestrak_status,
            last_updated_utc=last_updated,
            latency_seconds=latency,
            record_count=record_count,
        ),
        DataSourceStatus(
            name="SGP4 Orbit Propagator",
            source="sgp4 / Analytical TEME Engine",
            status="ONLINE",
            last_updated_utc=now_iso,
            latency_seconds=1,
            record_count=total_records,
        ),
    ]

    return sources
