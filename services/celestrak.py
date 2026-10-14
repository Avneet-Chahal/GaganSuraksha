import logging
import math
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any

import httpx
from sqlalchemy.orm import Session
from sqlalchemy import select
from sgp4.api import Satrec

from backend.models.db_models import SatelliteModel, IngestionStatusModel

logger = logging.getLogger("gagan_suraksha.celestrak")

# CelesTrak Endpoints and Configuration
CELESTRAK_GP_URL = "https://celestrak.org/NORAD/elements/gp.php"
USER_AGENT = "GaganSuraksha-SSA/1.0 (ISRO NETRA Conjunction Monitoring; istrac-ssa@isro.gov.in)"
DEFAULT_TIMEOUT = 10.0
CACHE_TTL_HOURS = 2.0

# Indian Primary Assets to monitor
INDIAN_NORAD_IDS = [43111, 44857, 51656, 45026, 54361, 41752, 40930, 43865]

KNOWN_INDIAN_METADATA: Dict[int, Dict[str, Any]] = {
    43111: {
        "name": "CARTOSAT-2F",
        "intl_designator": "2018-004A",
        "type": "PAYLOAD",
        "is_indian": True,
        "is_watchlist": True,
        "owner_country": "India (ISRO)",
        "operator": "ISRO ISTRAC",
    },
    44857: {
        "name": "RISAT-2BR1",
        "intl_designator": "2019-089A",
        "type": "PAYLOAD",
        "is_indian": True,
        "is_watchlist": True,
        "owner_country": "India (ISRO)",
        "operator": "ISRO ISTRAC",
    },
    51656: {
        "name": "EOS-04 (RISAT-1A)",
        "intl_designator": "2022-013A",
        "type": "PAYLOAD",
        "is_indian": True,
        "is_watchlist": True,
        "owner_country": "India (ISRO)",
        "operator": "ISRO ISTRAC",
    },
    45026: {
        "name": "GSAT-30",
        "intl_designator": "2020-005A",
        "type": "PAYLOAD",
        "is_indian": True,
        "is_watchlist": True,
        "owner_country": "India (ISRO)",
        "operator": "ISRO MCF Hassan",
    },
    54361: {
        "name": "OCEANSAT-3",
        "intl_designator": "2022-158A",
        "type": "PAYLOAD",
        "is_indian": True,
        "is_watchlist": True,
        "owner_country": "India (ISRO)",
        "operator": "ISRO ISTRAC",
    },
    41752: {
        "name": "SCATSAT-1",
        "intl_designator": "2016-059A",
        "type": "PAYLOAD",
        "is_indian": True,
        "is_watchlist": False,
        "owner_country": "India (ISRO)",
        "operator": "ISRO SAC Ahmedabad",
    },
    40930: {
        "name": "ASTROSAT",
        "intl_designator": "2015-052A",
        "type": "PAYLOAD",
        "is_indian": True,
        "is_watchlist": False,
        "owner_country": "India (ISRO)",
        "operator": "ISRO ISTRAC",
    },
    43865: {
        "name": "GSAT-7A",
        "intl_designator": "2018-105A",
        "type": "PAYLOAD",
        "is_indian": True,
        "is_watchlist": False,
        "owner_country": "India (ISRO)",
        "operator": "ISRO MCF Hassan",
    },
}

# Major Debris Groups on CelesTrak
DEBRIS_GROUPS = [
    ("cosmos-2251-debris", "Russia (CIS)"),
    ("iridium-33-debris", "United States"),
    ("fengyun-1c-debris", "China"),
]
MAX_DEBRIS_OBJECTS = 400


class CelesTrakError(Exception):
    """Base exception for CelesTrak ingestion errors."""
    pass


class RateLimitError(CelesTrakError):
    """Raised when CelesTrak returns HTTP 429 Too Many Requests."""
    pass


def compute_tle_checksum(line: str) -> int:
    """
    Computes the standard modulo-10 checksum for a 69-character TLE line.
    Sums numerical values of digits (0-9) and gives minus signs (-) a value of 1.
    All other characters contribute 0. The sum modulo 10 is the checksum.
    """
    if len(line) < 68:
        return -1
    total = sum(int(c) if c.isdigit() else (1 if c == "-" else 0) for c in line[:68])
    return total % 10


def validate_tle_record(line1: str, line2: str) -> Tuple[bool, Optional[str], Optional[Satrec]]:
    """
    Validates a Two-Line Element set before storage:
    1. Line 1 and Line 2 must be exactly 69 characters.
    2. Line 1 must start with '1 ' and Line 2 with '2 '.
    3. The modulo-10 checksum digit at index 68 must match the computed value.
    4. SGP4 Satrec.twoline2rv must return error code 0.
    5. Propagation at the TLE epoch must succeed without error (e == 0 and valid coordinates).

    Returns:
        (is_valid: bool, failure_reason: Optional[str], satrec: Optional[Satrec])
    """
    l1 = line1.rstrip("\r\n")
    l2 = line2.rstrip("\r\n")

    if len(l1) != 69:
        return False, f"Line 1 length is {len(l1)}, expected 69", None
    if len(l2) != 69:
        return False, f"Line 2 length is {len(l2)}, expected 69", None

    if not l1.startswith("1 "):
        return False, f"Line 1 does not start with '1 ': '{l1[:10]}'", None
    if not l2.startswith("2 "):
        return False, f"Line 2 does not start with '2 ': '{l2[:10]}'", None

    if not l1[68].isdigit():
        return False, f"Line 1 checksum character '{l1[68]}' is not a digit", None
    if not l2[68].isdigit():
        return False, f"Line 2 checksum character '{l2[68]}' is not a digit", None

    expected_chk1 = int(l1[68])
    calc_chk1 = compute_tle_checksum(l1)
    if calc_chk1 != expected_chk1:
        return False, f"Line 1 checksum mismatch: calculated {calc_chk1}, got {expected_chk1}", None

    expected_chk2 = int(l2[68])
    calc_chk2 = compute_tle_checksum(l2)
    if calc_chk2 != expected_chk2:
        return False, f"Line 2 checksum mismatch: calculated {calc_chk2}, got {expected_chk2}", None

    try:
        satrec = Satrec.twoline2rv(l1, l2)
    except Exception as exc:
        return False, f"SGP4 twoline2rv exception: {exc}", None

    if satrec.error != 0:
        return False, f"SGP4 initialization error code: {satrec.error}", None

    # Verify propagation at epoch
    try:
        err_code, r_km, v_km_s = satrec.sgp4(satrec.jdsatepoch, satrec.jdsatepochF)
        if err_code != 0:
            return False, f"SGP4 epoch propagation error code: {err_code}", None
        if any(math.isnan(coord) for coord in r_km) or any(math.isnan(coord) for coord in v_km_s):
            return False, "SGP4 epoch propagation produced NaN coordinates", None
    except Exception as exc:
        return False, f"SGP4 propagation exception at epoch: {exc}", None

    return True, None, satrec


def derive_orbital_parameters(satrec: Satrec, line1: Optional[str] = None) -> Dict[str, Any]:
    """
    Derives orbital parameters (apogee, perigee, altitude, inclination, period,
    velocity, regime, and epoch) from an SGP4 Satrec object.
    Regime:
      - LEO: altitude < 2000 km
      - GEO: 35000 km to 36500 km with eccentricity < 0.2
      - HEO: eccentricity >= 0.25
      - MEO: other (e.g. 2000 km to 35000 km)
    """
    mu_earth = 398600.4418  # km^3 / s^2 (standard Earth gravitational parameter)
    re_earth = 6378.137     # km (WGS-72 / WGS-84 standard equatorial Earth radius)

    # satrec.no_kozai is mean motion in rad/min
    n_rad_s = satrec.no_kozai / 60.0
    a_km = (mu_earth / (n_rad_s ** 2)) ** (1.0 / 3.0)
    ecc = float(satrec.ecco)

    perigee_km = a_km * (1.0 - ecc) - re_earth
    apogee_km = a_km * (1.0 + ecc) - re_earth
    altitude_km = a_km - re_earth
    inclination_deg = math.degrees(satrec.inclo)
    period_min = (2.0 * math.pi) / satrec.no_kozai

    _, _, v_epoch = satrec.sgp4(satrec.jdsatepoch, satrec.jdsatepochF)
    vel_km_s = math.sqrt(v_epoch[0] ** 2 + v_epoch[1] ** 2 + v_epoch[2] ** 2)

    # Orbital regime classification
    if altitude_km < 2000.0:
        regime = "LEO"
    elif 35000.0 <= altitude_km <= 36500.0 and ecc < 0.2:
        regime = "GEO"
    elif ecc >= 0.25:
        regime = "HEO"
    else:
        regime = "MEO"

    # Derive TLE epoch in ISO UTC string
    tle_epoch_iso = datetime.now(timezone.utc).isoformat()
    if line1 and len(line1) >= 32:
        try:
            epoch_str = line1[18:32].strip()
            yy = int(epoch_str[:2])
            year = 1900 + yy if yy >= 57 else 2000 + yy
            day_fraction = float(epoch_str[2:])
            epoch_dt = datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(days=day_fraction - 1)
            tle_epoch_iso = epoch_dt.isoformat().replace("+00:00", "Z")
        except Exception:
            pass

    return {
        "apogee_km": round(apogee_km, 2),
        "perigee_km": round(perigee_km, 2),
        "altitude_km": round(altitude_km, 2),
        "inclination_deg": round(inclination_deg, 4),
        "period_min": round(period_min, 2),
        "velocity_km_s": round(vel_km_s, 3),
        "regime": regime,
        "tle_epoch": tle_epoch_iso,
    }


def parse_celestrak_tle_stream(text: str) -> List[Tuple[Optional[str], str, str]]:
    """
    Parses raw TLE text stream from CelesTrak into a list of (name, line1, line2).
    Handles both 3-line format (Name, Line 1, Line 2) and 2-line format.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    records: List[Tuple[Optional[str], str, str]] = []

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("1 ") and len(line) == 69 and (i + 1 < len(lines)) and lines[i + 1].startswith("2 ") and len(lines[i + 1]) == 69:
            name = None
            if i > 0:
                prev_line = lines[i - 1]
                if not prev_line.startswith("1 ") and not prev_line.startswith("2 "):
                    name = prev_line[2:].strip() if prev_line.startswith("0 ") else prev_line.strip()
            records.append((name, line, lines[i + 1]))
            i += 2
        else:
            i += 1

    return records


def fetch_with_retry(
    client: httpx.Client,
    url: str,
    params: dict,
    max_retries: int = 2,
    initial_backoff: float = 0.5,
) -> str:
    """
    Executes an HTTP GET request with retries and exponential backoff.
    Raises RateLimitError if CelesTrak returns HTTP 429.
    Raises httpx.HTTPError on failure after max_retries.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            resp = client.get(url, params=params)
            if resp.status_code == 429:
                logger.warning("CelesTrak rate limit reached (HTTP 429). Backing off.")
                raise RateLimitError("CelesTrak rate limit exceeded (HTTP 429)")
            resp.raise_for_status()
            return resp.text
        except RateLimitError:
            raise
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
            last_exc = exc
            if attempt < max_retries:
                time.sleep(initial_backoff * (2 ** attempt))
            else:
                break

    if last_exc:
        raise last_exc
    raise CelesTrakError("Failed to fetch data after retries")


def refresh_celestrak_data(
    db: Session,
    force: bool = False,
    client: Optional[httpx.Client] = None,
) -> Tuple[bool, str]:
    """
    Refreshes TLE data from CelesTrak GP API:
    - Checks 2-hour rate-limit cache (skips if updated < 2 hours ago unless force=True).
    - Fetches primary Indian satellites (NORAD IDs).
    - Fetches debris groups capped at 400 total debris items.
    - Validates 69 chars, checksum, and SGP4 propagation at epoch for each record.
    - Upserts valid records into SatelliteModel table with data_source='CELESTRAK'.
    - Updates ingestion_status table with latency, record count, and operational status.
    - Keeps synthetic data untouched if fetch fails.
    """
    now_utc = datetime.now(timezone.utc)
    now_iso = now_utc.isoformat()

    # Query or create ingestion_status row
    status_row = db.query(IngestionStatusModel).filter(IngestionStatusModel.id == 1).first()
    if not status_row:
        status_row = IngestionStatusModel(
            id=1,
            source_name="CelesTrak GP API",
            status="STANDBY",
            record_count=0,
            latency_seconds=0.0,
        )
        db.add(status_row)
        db.flush()

    # 2-hour Fair-Use Cache Check
    if not force and status_row.last_success_utc:
        try:
            last_success_dt = datetime.fromisoformat(status_row.last_success_utc.replace("Z", "+00:00"))
            if now_utc - last_success_dt < timedelta(hours=CACHE_TTL_HOURS):
                msg = f"CelesTrak cache is fresh (last updated at {status_row.last_success_utc}). Skipping fetch."
                logger.info(msg)
                return True, msg
        except Exception:
            pass

    t0 = time.perf_counter()
    status_row.last_fetch_utc = now_iso

    own_client = False
    if client is None:
        client = httpx.Client(
            timeout=DEFAULT_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )
        own_client = True

    fetched_records: List[Tuple[Optional[str], str, str, str]] = []  # (name, l1, l2, category)
    last_fetch_error: Optional[Exception] = None

    try:
        # 1. Fetch Indian primary operational satellites by NORAD ID
        for catnr in INDIAN_NORAD_IDS:
            try:
                body = fetch_with_retry(
                    client,
                    CELESTRAK_GP_URL,
                    params={"CATNR": catnr, "FORMAT": "tle"},
                )
                items = parse_celestrak_tle_stream(body)
                for name, l1, l2 in items:
                    fetched_records.append((name, l1, l2, "INDIAN"))
            except RateLimitError as exc:
                last_fetch_error = exc
                logger.warning("CelesTrak rate limit hit during Indian satellite fetch: %s", exc)
                break
            except Exception as exc:
                last_fetch_error = exc
                logger.warning("Failed to fetch Indian satellite %d: %s", catnr, exc)

        # 2. Fetch Debris groups capped at 400 objects (if not rate limited)
        if not isinstance(last_fetch_error, RateLimitError):
            debris_count = 0
            for group_name, group_owner in DEBRIS_GROUPS:
                if debris_count >= MAX_DEBRIS_OBJECTS:
                    break
                try:
                    body = fetch_with_retry(
                        client,
                        CELESTRAK_GP_URL,
                        params={"GROUP": group_name, "FORMAT": "tle"},
                    )
                    items = parse_celestrak_tle_stream(body)
                    for name, l1, l2 in items:
                        if debris_count >= MAX_DEBRIS_OBJECTS:
                            break
                        fetched_records.append((name, l1, l2, group_name))
                        debris_count += 1
                except RateLimitError as exc:
                    last_fetch_error = exc
                    logger.warning("CelesTrak rate limit hit during debris fetch: %s", exc)
                    break
                except Exception as exc:
                    last_fetch_error = exc
                    logger.warning("Failed to fetch debris group %s: %s", group_name, exc)

        if not fetched_records:
            if last_fetch_error:
                raise last_fetch_error
            raise CelesTrakError("No records could be retrieved from CelesTrak API")

        # 3. Validate and Upsert into SatelliteModel
        seen_norad_ids: set[int] = set()
        saved_count = 0
        for name_raw, l1, l2, category in fetched_records:
            is_valid, reason, satrec = validate_tle_record(l1, l2)
            if not is_valid or satrec is None:
                logger.warning("Skipping invalid TLE: %s. Line 1: %s", reason, l1[:20])
                continue

            try:
                norad_id = int(l1[2:7])
            except ValueError:
                continue

            if norad_id in seen_norad_ids:
                continue
            seen_norad_ids.add(norad_id)

            sat_id = str(norad_id)
            derived = derive_orbital_parameters(satrec, l1)

            # Metadata resolution
            if norad_id in KNOWN_INDIAN_METADATA:
                meta = KNOWN_INDIAN_METADATA[norad_id]
                sat_name = meta["name"]
                intl_des = meta["intl_designator"]
                sat_type = meta["type"]
                is_indian = meta["is_indian"]
                is_watchlist = meta["is_watchlist"]
                owner = meta["owner_country"]
                operator = meta["operator"]
            else:
                sat_name = name_raw or f"DEBRIS-{norad_id}"
                intl_des = l1[9:17].strip()
                sat_type = "DEBRIS"
                is_indian = False
                is_watchlist = False
                owner = "Space Debris"
                operator = None

            existing_sat = db.query(SatelliteModel).filter(SatelliteModel.norad_id == norad_id).first()
            if existing_sat:
                existing_sat.name = sat_name
                existing_sat.intl_designator = intl_des
                existing_sat.type = sat_type
                existing_sat.regime = derived["regime"]
                existing_sat.is_indian = is_indian
                existing_sat.is_watchlist = is_watchlist
                existing_sat.owner_country = owner
                existing_sat.operator = operator
                existing_sat.apogee_km = derived["apogee_km"]
                existing_sat.perigee_km = derived["perigee_km"]
                existing_sat.altitude_km = derived["altitude_km"]
                existing_sat.inclination_deg = derived["inclination_deg"]
                existing_sat.period_min = derived["period_min"]
                existing_sat.velocity_km_s = derived["velocity_km_s"]
                existing_sat.tle_epoch = derived["tle_epoch"]
                existing_sat.tle_line1 = l1
                existing_sat.tle_line2 = l2
                existing_sat.data_source = "CELESTRAK"
            else:
                new_sat = SatelliteModel(
                    id=sat_id,
                    norad_id=norad_id,
                    name=sat_name,
                    intl_designator=intl_des,
                    type=sat_type,
                    regime=derived["regime"],
                    is_indian=is_indian,
                    is_watchlist=is_watchlist,
                    owner_country=owner,
                    operator=operator,
                    apogee_km=derived["apogee_km"],
                    perigee_km=derived["perigee_km"],
                    altitude_km=derived["altitude_km"],
                    inclination_deg=derived["inclination_deg"],
                    period_min=derived["period_min"],
                    velocity_km_s=derived["velocity_km_s"],
                    tle_epoch=derived["tle_epoch"],
                    tle_line1=l1,
                    tle_line2=l2,
                    data_source="CELESTRAK",
                )
                db.add(new_sat)

            saved_count += 1

        db.flush()

        # Update Ingestion Status
        latency = time.perf_counter() - t0
        status_row.status = "ONLINE"
        status_row.last_success_utc = now_iso
        status_row.record_count = saved_count
        status_row.latency_seconds = round(latency, 2)
        status_row.error_message = None
        db.commit()

        success_msg = f"Successfully ingested {saved_count} satellites/debris from CelesTrak in {latency:.2f}s."
        logger.info(success_msg)
        return True, success_msg

    except Exception as exc:
        latency = time.perf_counter() - t0
        status_row.status = "DEGRADED"
        status_row.latency_seconds = round(latency, 2)
        status_row.error_message = str(exc)
        db.commit()
        err_msg = f"CelesTrak ingestion failed: {exc}"
        logger.error(err_msg)
        return False, err_msg

    finally:
        if own_client and client:
            client.close()
