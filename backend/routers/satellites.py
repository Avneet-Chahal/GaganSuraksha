from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import select
from backend.database import get_db
from backend.models.db_models import SatelliteModel
from backend.schemas.types import SatelliteRecord

router = APIRouter(prefix="/satellites", tags=["Satellites"])


@router.get("", response_model=List[SatelliteRecord])
def get_satellites(
    regime: Optional[str] = Query(None, description="Filter by orbit regime (LEO, MEO, GEO, HEO)"),
    is_indian: Optional[bool] = Query(None, description="Filter by Indian nationality"),
    is_watchlist: Optional[bool] = Query(None, description="Filter by watchlist status"),
    type: Optional[str] = Query(None, description="Filter by satellite type (PAYLOAD, DEBRIS, etc.)"),
    search: Optional[str] = Query(None, description="Search by name or international designator"),
    db: Session = Depends(get_db),
) -> List[SatelliteRecord]:
    """Retrieves all tracked satellites and space debris objects."""
    stmt = select(SatelliteModel)

    if regime:
        stmt = stmt.where(SatelliteModel.regime == regime.upper())
    if is_indian is not None:
        stmt = stmt.where(SatelliteModel.is_indian == is_indian)
    if is_watchlist is not None:
        stmt = stmt.where(SatelliteModel.is_watchlist == is_watchlist)
    if type:
        stmt = stmt.where(SatelliteModel.type == type.upper())
    if search:
        search_pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            SatelliteModel.name.ilike(search_pattern)
            | SatelliteModel.intl_designator.ilike(search_pattern)
            | SatelliteModel.id.ilike(search_pattern)
        )

    satellites = db.scalars(stmt).all()
    return [SatelliteRecord.model_validate(sat) for sat in satellites]
