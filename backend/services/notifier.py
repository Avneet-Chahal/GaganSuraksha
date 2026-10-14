"""
Proxy service re-exporting notification and alert dispatch functions from services.notifier.
"""
from services.notifier import (
    mask_url,
    validate_webhook_url,
    send_webhook_alert,
    send_telegram_alert,
    send_email_alert,
    format_alert_message,
    process_screening_alerts,
)

__all__ = [
    "mask_url",
    "validate_webhook_url",
    "send_webhook_alert",
    "send_telegram_alert",
    "send_email_alert",
    "format_alert_message",
    "process_screening_alerts",
]
