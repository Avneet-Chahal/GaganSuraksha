from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import select
from backend.database import get_db
from backend.models.db_models import WatchlistItem, SatelliteModel
from backend.schemas.types import WatchlistItemRecord, WatchlistItemCreate

router = APIRouter(prefix="/watchlist", tags=["Watchlist"])


@router.get("", response_model=List[WatchlistItemRecord])
def get_watchlist_items(
    active_only: bool = Query(False, description="Filter for active watchlist items only"),
    db: Session = Depends(get_db),
) -> List[WatchlistItemRecord]:
    """Retrieves all tracked Indian space assets on the collision surveillance watchlist."""
    stmt = select(WatchlistItem)
    if active_only:
        stmt = stmt.where(WatchlistItem.active == True)
    items = db.scalars(stmt).all()
    return [WatchlistItemRecord.model_validate(item) for item in items]


@router.post("", response_model=WatchlistItemRecord, status_code=status.HTTP_201_CREATED)
def add_or_update_watchlist_item(
    item_in: WatchlistItemCreate,
    db: Session = Depends(get_db),
) -> WatchlistItemRecord:
    """
    Adds a new space asset to the active collision watchlist or updates an existing item.
    Also flags the underlying Satellite record with is_watchlist = True.
    """
    # Check if satellite with norad_id already exists in watchlist
    stmt = select(WatchlistItem).where(WatchlistItem.norad_id == item_in.norad_id)
    existing_item = db.scalars(stmt).first()

    now_iso = datetime.now(timezone.utc).isoformat()

    if existing_item:
        existing_item.name = item_in.name
        existing_item.regime = item_in.regime
        existing_item.custom_pc_threshold = item_in.custom_pc_threshold
        existing_item.custom_miss_distance_km = item_in.custom_miss_distance_km
        existing_item.active = item_in.active
        watchlist_obj = existing_item
    else:
        watchlist_obj = WatchlistItem(
            id=str(item_in.norad_id),
            norad_id=item_in.norad_id,
            name=item_in.name,
            regime=item_in.regime,
            custom_pc_threshold=item_in.custom_pc_threshold,
            custom_miss_distance_km=item_in.custom_miss_distance_km,
            added_at=now_iso,
            active=item_in.active,
        )
        db.add(watchlist_obj)

    # Sync matching satellite model if present in database
    sat_stmt = select(SatelliteModel).where(
        (SatelliteModel.norad_id == item_in.norad_id) | (SatelliteModel.id == str(item_in.norad_id))
    )
    satellite = db.scalars(sat_stmt).first()
    if satellite:
        satellite.is_watchlist = True

    db.commit()
    db.refresh(watchlist_obj)
    return WatchlistItemRecord.model_validate(watchlist_obj)


@router.delete("", status_code=status.HTTP_200_OK)
def delete_watchlist_item(
    id: Optional[str] = Query(None, description="Watchlist item ID to remove"),
    norad_id: Optional[int] = Query(None, description="NORAD catalog ID to remove"),
    db: Session = Depends(get_db),
) -> dict:
    """Removes a space asset from the collision watchlist via query parameters."""
    if not id and norad_id is None:
        raise HTTPException(status_code=400, detail="Must provide either 'id' or 'norad_id' to delete from watchlist.")

    stmt = select(WatchlistItem)
    if id:
        stmt = stmt.where(WatchlistItem.id == id)
    elif norad_id is not None:
        stmt = stmt.where(WatchlistItem.norad_id == norad_id)

    item = db.scalars(stmt).first()
    if not item:
        raise HTTPException(status_code=404, detail="Watchlist asset not found.")

    deleted_id = item.id
    deleted_norad = item.norad_id
    db.delete(item)

    # Update satellite record if present
    sat_stmt = select(SatelliteModel).where(
        (SatelliteModel.norad_id == deleted_norad) | (SatelliteModel.id == deleted_id)
    )
    satellite = db.scalars(sat_stmt).first()
    if satellite:
        satellite.is_watchlist = False

    db.commit()
    return {"status": "DELETED", "id": deleted_id, "noradId": deleted_norad}


@router.delete("/{item_id}", status_code=status.HTTP_200_OK)
def delete_watchlist_item_by_path(
    item_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """Removes a space asset from the collision watchlist via path parameter."""
    stmt = select(WatchlistItem).where(WatchlistItem.id == item_id)
    item = db.scalars(stmt).first()
    if not item:
        # Try finding by norad_id if numeric
        if item_id.isdigit():
            stmt = select(WatchlistItem).where(WatchlistItem.norad_id == int(item_id))
            item = db.scalars(stmt).first()

    if not item:
        raise HTTPException(status_code=404, detail="Watchlist asset not found.")

    deleted_id = item.id
    deleted_norad = item.norad_id
    db.delete(item)

    # Update satellite record if present
    sat_stmt = select(SatelliteModel).where(
        (SatelliteModel.norad_id == deleted_norad) | (SatelliteModel.id == deleted_id)
    )
    satellite = db.scalars(sat_stmt).first()
    if satellite:
        satellite.is_watchlist = False

    db.commit()
    return {"status": "DELETED", "id": deleted_id, "noradId": deleted_norad}
