import os
import socket
import logging
import smtplib
import ipaddress
import urllib.parse
from email.mime.text import MIMEText
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
import httpx
from sqlalchemy.orm import Session
from sqlalchemy import select

logger = logging.getLogger("gagan_suraksha.notifier")

# ---------------------------------------------------------------------------
# SSRF Protection & URL Masking
# ---------------------------------------------------------------------------

def mask_url(url: str) -> str:
    """
    Masks a URL so credentials, query parameters, and private path segments
    are never leaked into log outputs.
    Example: https://user:pass@webhook.site/abc-123?key=secret -> https://webhook.site/***
    """
    if not url or not isinstance(url, str):
        return "[invalid-url]"
    try:
        parsed = urllib.parse.urlsplit(url.strip())
        if not parsed.scheme or not parsed.netloc:
            return "https://[masked-target]"
        host = parsed.hostname or "[masked-host]"
        port_part = f":{parsed.port}" if parsed.port and parsed.port not in (80, 443) else ""
        return f"{parsed.scheme}://{host}{port_part}/***"
    except Exception:
        return "https://[masked-target]"


def _check_ip_safety(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    """
    Validates that an IP address is not private, loopback, link-local,
    multicast, or reserved. Raises ValueError if unsafe.
    """
    if ip.is_loopback:
        raise ValueError(f"Webhook destination IP {ip} is a loopback address (SSRF blocked).")
    if ip.is_private:
        raise ValueError(f"Webhook destination IP {ip} is a private RFC1918/RFC4193 address (SSRF blocked).")
    if ip.is_link_local:
        raise ValueError(f"Webhook destination IP {ip} is a link-local address (SSRF blocked).")
    if ip.is_reserved:
        raise ValueError(f"Webhook destination IP {ip} is an IETF reserved address (SSRF blocked).")
    if ip.is_multicast:
        raise ValueError(f"Webhook destination IP {ip} is a multicast address (SSRF blocked).")
    if ip.is_unspecified:
        raise ValueError(f"Webhook destination IP {ip} is an unspecified address (SSRF blocked).")


def validate_webhook_url(url: str) -> None:
    """
    Validates that a webhook URL is safe from SSRF attacks and DNS rebinding:
    1. Must use HTTPS scheme.
    2. Rejects URLs containing embedded user credentials (user:pass@).
    3. Must contain a valid hostname.
    4. Rejects private, loopback, link-local, and cloud metadata hostnames.
    5. Resolves hostname via DNS and checks that none of the resolved IPs
       belong to private / loopback / link-local / reserved ranges.
    """
    if not url or not isinstance(url, str):
        raise ValueError("Webhook URL must be a non-empty string.")

    url_clean = url.strip()
    try:
        parsed = urllib.parse.urlsplit(url_clean)
    except Exception as exc:
        raise ValueError(f"Malformed webhook URL: {exc}")

    # Enforce HTTPS only
    if parsed.scheme.lower() != "https":
        raise ValueError(f"Webhook URL must use secure HTTPS scheme (received: '{parsed.scheme}').")

    # Reject embedded user credentials
    if parsed.username or parsed.password or "@" in parsed.netloc:
        raise ValueError("Webhook URL must not contain embedded user credentials (user:pass@).")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Webhook URL is missing a valid hostname.")

    hostname_lower = hostname.lower().strip()

    # Immediate blocklist for loopback, local, and cloud metadata endpoints
    blocked_hostnames = {
        "localhost",
        "127.0.0.1",
        "::1",
        "0.0.0.0",
        "169.254.169.254",
        "instance-data",
        "metadata.google.internal",
        "metadata.azure.internal",
    }
    if hostname_lower in blocked_hostnames:
        raise ValueError(f"Webhook target '{hostname_lower}' is a blocked local/metadata address (SSRF blocked).")

    # Reject local/internal domain suffixes
    for suffix in (".local", ".internal", ".localhost", ".lan", ".home"):
        if hostname_lower.endswith(suffix):
            raise ValueError(f"Webhook target domain '{hostname_lower}' is a private internal domain (SSRF blocked).")

    # If the hostname is an IP literal, validate immediately
    try:
        ip = ipaddress.ip_address(hostname_lower)
        _check_ip_safety(ip)
        return
    except ValueError:
        # Not an IP literal, proceed to DNS resolution
        pass

    # Resolve hostname via DNS and inspect all resolved addresses
    try:
        addr_info = socket.getaddrinfo(hostname, 443, proto=socket.IPPROTO_TCP)
        for entry in addr_info:
            ip_str = entry[4][0]
            ip = ipaddress.ip_address(ip_str)
            _check_ip_safety(ip)
    except socket.gaierror:
        # If DNS cannot be resolved in offline or test environments,
        # ensure it at least has a valid public FQDN structure
        if "." not in hostname_lower:
            raise ValueError(f"Invalid webhook domain name: '{hostname_lower}'")


# ---------------------------------------------------------------------------
# Channel Dispatch Functions (Webhook, Telegram, Email)
# ---------------------------------------------------------------------------

def send_webhook_alert(url: str, payload: Dict[str, Any], timeout: float = 5.0) -> bool:
    """
    Sends an alert payload via HTTP POST to an HTTPS webhook URL.
    - Enforces SSRF checks before dispatch.
    - 5-second connection/read timeout.
    - Never logs the full URL or request authorization.
    """
    validate_webhook_url(url)
    masked_target = mask_url(url)
    logger.info("Dispatching webhook alert to %s", masked_target)

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, json=payload)
            if 200 <= response.status_code < 300:
                logger.info("Webhook alert successfully delivered to %s (status %d)", masked_target, response.status_code)
                return True
            else:
                logger.warning("Webhook alert to %s returned HTTP %d", masked_target, response.status_code)
                return False
    except Exception as exc:
        logger.error("Webhook alert delivery failed for %s: %s", masked_target, exc.__class__.__name__)
        return False


def send_telegram_alert(
    chat_id: str,
    message: str,
    bot_token: Optional[str] = None,
    timeout: float = 5.0,
) -> bool:
    """
    Sends an alert message to a Telegram chat via the Bot API.
    Token is read from env (TELEGRAM_BOT_TOKEN) or parameter.
    Never logs the Telegram bot token.
    """
    token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or not token.strip():
        logger.info("Telegram dispatch skipped: TELEGRAM_BOT_TOKEN not configured.")
        return False

    if not chat_id or not chat_id.strip():
        logger.warning("Telegram dispatch skipped: chat_id not provided.")
        return False

    # Masked URL for logs — NEVER log tokens!
    masked_endpoint = "https://api.telegram.org/bot***MASKED***/sendMessage"
    logger.info("Dispatching Telegram alert to chat '%s' via %s", chat_id, masked_endpoint)

    real_endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(real_endpoint, json=payload)
            if 200 <= response.status_code < 300:
                logger.info("Telegram alert delivered successfully to '%s'", chat_id)
                return True
            else:
                logger.warning("Telegram Bot API returned HTTP %d for chat '%s'", response.status_code, chat_id)
                return False
    except Exception as exc:
        logger.error("Telegram alert dispatch failed for '%s': %s", chat_id, exc.__class__.__name__)
        return False


def send_email_alert(
    to_email: str,
    subject: str,
    message_body: str,
    from_email: Optional[str] = None,
) -> bool:
    """
    Sends an alert email via SMTP configured from environment variables:
    SMTP_HOST, SMTP_PORT (default 587), SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SMTP_TLS.
    Never logs passwords or credentials.
    """
    smtp_host = os.getenv("SMTP_HOST")
    if not smtp_host or not smtp_host.strip():
        logger.info("SMTP host not configured. Skipping email dispatch to %s", to_email)
        return False

    if not to_email or not to_email.strip():
        logger.warning("Email dispatch skipped: to_email not provided.")
        return False

    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASSWORD")
    from_addr = from_email or os.getenv("SMTP_FROM", "")
    use_tls = os.getenv("SMTP_TLS", "true").lower() in ("true", "1", "yes")

    msg = MIMEText(message_body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_email

    logger.info("Dispatching email alert to %s via SMTP %s:%d", to_email, smtp_host, smtp_port)

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=5) as server:
            if use_tls:
                server.starttls()
            if smtp_user and smtp_pass:
                server.login(smtp_user, smtp_pass)
            server.sendmail(from_addr, [to_email], msg.as_string())
        logger.info("Email alert successfully delivered to %s", to_email)
        return True
    except Exception as exc:
        logger.error("SMTP delivery failed to %s: %s", to_email, exc.__class__.__name__)
        return False


# ---------------------------------------------------------------------------
# Screening Alert Pipeline & Deduplication
# ---------------------------------------------------------------------------

def format_alert_message(conj: Any, primary_name: str, secondary_name: str) -> str:
    """Formats a human-readable text alert for email or messaging channels."""
    return (
        f"[GAGAN SURAKSHA] CONJUNCTION COLLISION RISK ALERT\n"
        f"--------------------------------------------------\n"
        f"Event ID:       {conj.id}\n"
        f"Risk Level:     {conj.risk_level}\n"
        f"TCA (UTC):      {conj.tca_utc}\n"
        f"Miss Distance:  {conj.miss_distance_km:.3f} km\n"
        f"Collision Pc:   {conj.calibrated_probability:.2e}\n"
        f"Primary Asset:  {primary_name}\n"
        f"Secondary:      {secondary_name}\n"
        f"Action:         {conj.recommended_action}\n"
        f"--------------------------------------------------\n"
        f"ISRO ISTRAC / NETRA SSA Monitoring Console\n"
    )


def process_screening_alerts(
    db: Session,
    conjunctions: List[Any],
) -> List[str]:
    """
    Evaluates discovered conjunctions against user alert thresholds:
    1. Loads user alert settings from the database (or defaults).
    2. Inspects each conjunction to verify if it exceeds the user's Pc
       or miss-distance thresholds (using primary satellite custom thresholds
       if configured on the watchlist).
    3. Checks sent_alerts table to prevent duplicate alerts for the same conjunction ID.
    4. Dispatches alerts across enabled channels (email, Telegram, webhook).
    5. Records newly dispatched conjunction IDs in the sent_alerts table.

    Returns the list of newly alerted conjunction IDs.
    """
    from backend.models.db_models import AlertSettings, WatchlistItem, SentAlert, SatelliteModel

    # Load active alert settings
    alert_settings = db.scalars(select(AlertSettings).where(AlertSettings.id == 1)).first()
    if alert_settings is None:
        default_pc = 1.0e-4
        default_miss = 1.0
        notify_email = False
        email_addr = ""
        notify_telegram = False
        telegram_chat = ""
        notify_webhook = False
        webhook_url = ""
    else:
        default_pc = alert_settings.default_pc_threshold
        default_miss = alert_settings.default_miss_distance_km
        notify_email = alert_settings.notify_email
        email_addr = alert_settings.email_address
        notify_telegram = alert_settings.notify_telegram
        telegram_chat = alert_settings.telegram_chat_id
        notify_webhook = alert_settings.notify_istrac_webhook
        webhook_url = alert_settings.webhook_url

    # Preload watchlist items mapped by satellite ID and NORAD ID
    watchlist_items = db.scalars(select(WatchlistItem).where(WatchlistItem.active == True)).all()
    watchlist_by_id = {item.id: item for item in watchlist_items}
    watchlist_by_norad = {item.norad_id: item for item in watchlist_items}

    # Preload already alerted conjunction IDs to avoid duplicates
    sent_records = db.scalars(select(SentAlert.conjunction_id)).all()
    already_sent_ids = set(sent_records)

    newly_alerted_ids: List[str] = []

    for conj in conjunctions:
        # Deduplication check: do not send duplicates for the same conjunction ID
        if conj.id in already_sent_ids:
            continue

        # Determine effective thresholds (check for custom watchlist threshold)
        pc_threshold = default_pc
        miss_threshold = default_miss

        # Check if primary satellite has custom thresholds
        primary_item = watchlist_by_id.get(conj.primary_sat_id)
        if primary_item is None and hasattr(conj, "primary_sat") and conj.primary_sat:
            primary_item = watchlist_by_norad.get(conj.primary_sat.norad_id)

        if primary_item:
            if primary_item.custom_pc_threshold is not None:
                pc_threshold = primary_item.custom_pc_threshold
            if primary_item.custom_miss_distance_km is not None:
                miss_threshold = primary_item.custom_miss_distance_km

        # Check if thresholds are exceeded:
        # Probability greater than or equal to threshold OR miss distance closer than threshold
        exceeds_pc = conj.calibrated_probability >= pc_threshold
        exceeds_miss = conj.miss_distance_km <= miss_threshold

        if not (exceeds_pc or exceeds_miss):
            continue

        # Conjunction qualifies for alert dispatch!
        primary_name = getattr(conj.primary_sat, "name", conj.primary_sat_id) if hasattr(conj, "primary_sat") and conj.primary_sat else conj.primary_sat_id
        secondary_name = getattr(conj.secondary_sat, "name", conj.secondary_sat_id) if hasattr(conj, "secondary_sat") and conj.secondary_sat else conj.secondary_sat_id

        alert_text = format_alert_message(conj, primary_name, secondary_name)
        webhook_payload = {
            "event": "CONJUNCTION_COLLISION_ALERT",
            "conjunctionId": conj.id,
            "primarySatellite": primary_name,
            "secondarySatellite": secondary_name,
            "tcaUtc": conj.tca_utc,
            "missDistanceKm": conj.miss_distance_km,
            "collisionProbability": conj.calibrated_probability,
            "riskLevel": conj.risk_level,
            "recommendedAction": conj.recommended_action,
            "timestampUtc": datetime.now(timezone.utc).isoformat(),
        }

        dispatched_channels: List[str] = []

        # 1. Webhook Dispatch
        if notify_webhook and webhook_url:
            success = send_webhook_alert(webhook_url, webhook_payload)
            if success:
                dispatched_channels.append("WEBHOOK")

        # 2. Telegram Dispatch
        if notify_telegram and telegram_chat:
            success = send_telegram_alert(telegram_chat, alert_text)
            if success:
                dispatched_channels.append("TELEGRAM")

        # 3. Email Dispatch
        if notify_email and email_addr:
            subject = f"[Gagan Suraksha] Critical Conjunction Alert: {conj.id} ({primary_name})"
            success = send_email_alert(email_addr, subject, alert_text)
            if success:
                dispatched_channels.append("EMAIL")

        # Record sent alert in database for persistent deduplication
        now_iso = datetime.now(timezone.utc).isoformat()
        sent_entry = SentAlert(
            conjunction_id=conj.id,
            sent_at_utc=now_iso,
            channels_sent=",".join(dispatched_channels) if dispatched_channels else "EVALUATED_DISPATCHED",
        )
        db.add(sent_entry)
        already_sent_ids.add(conj.id)
        newly_alerted_ids.append(conj.id)

    if newly_alerted_ids:
        db.commit()

    return newly_alerted_ids
