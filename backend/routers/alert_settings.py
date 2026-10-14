from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select
from backend.database import get_db
from backend.models.db_models import AlertSettings
from backend.schemas.types import AlertSettingsRecord, AlertSettingsUpdate
from services.notifier import validate_webhook_url

router = APIRouter(prefix="/alert-settings", tags=["AlertSettings"])


@router.get("", response_model=AlertSettingsRecord)
def get_alert_settings(
    db: Session = Depends(get_db),
) -> AlertSettingsRecord:
    """Retrieves current collision alert thresholds and notification channel settings."""
    stmt = select(AlertSettings).where(AlertSettings.id == 1)
    settings = db.scalars(stmt).first()

    if not settings:
        settings = AlertSettings(
            id=1,
            default_pc_threshold=1.0e-4,
            default_miss_distance_km=1.0,
            notify_email=False,
            email_address="",
            notify_telegram=False,
            telegram_chat_id="",
            notify_istrac_webhook=False,
            webhook_url="",
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)

    return AlertSettingsRecord.model_validate(settings)


@router.put("", response_model=AlertSettingsRecord)
def update_alert_settings(
    update_in: AlertSettingsUpdate,
    db: Session = Depends(get_db),
) -> AlertSettingsRecord:
    """
    Updates collision alert thresholds and notification dispatch channels.
    Validates webhook URL against SSRF attacks (HTTPS only, non-private IP).
    """
    stmt = select(AlertSettings).where(AlertSettings.id == 1)
    settings = db.scalars(stmt).first()

    if not settings:
        settings = AlertSettings(id=1)
        db.add(settings)

    # Validate webhook URL if updated and non-empty
    if update_in.webhook_url is not None and update_in.webhook_url.strip():
        try:
            validate_webhook_url(update_in.webhook_url.strip())
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid webhook URL (SSRF security check failed): {str(exc)}",
            )

    # Apply updates
    if update_in.default_pc_threshold is not None:
        if update_in.default_pc_threshold <= 0.0 or update_in.default_pc_threshold > 1.0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Default Pc threshold must be strictly between 0.0 and 1.0.",
            )
        settings.default_pc_threshold = update_in.default_pc_threshold

    if update_in.default_miss_distance_km is not None:
        if update_in.default_miss_distance_km <= 0.0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Default miss distance must be greater than 0 km.",
            )
        settings.default_miss_distance_km = update_in.default_miss_distance_km

    if update_in.notify_email is not None:
        settings.notify_email = update_in.notify_email
    if update_in.email_address is not None:
        settings.email_address = update_in.email_address

    if update_in.notify_telegram is not None:
        settings.notify_telegram = update_in.notify_telegram
    if update_in.telegram_chat_id is not None:
        settings.telegram_chat_id = update_in.telegram_chat_id

    if update_in.notify_istrac_webhook is not None:
        settings.notify_istrac_webhook = update_in.notify_istrac_webhook
    if update_in.webhook_url is not None:
        settings.webhook_url = update_in.webhook_url.strip()

    db.commit()
    db.refresh(settings)
    return AlertSettingsRecord.model_validate(settings)
