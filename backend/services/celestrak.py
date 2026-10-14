"""
Proxy module re-exporting services.celestrak for backend namespace consistency.
"""
from services.celestrak import (
    CELESTRAK_GP_URL,
    USER_AGENT,
    DEFAULT_TIMEOUT,
    CACHE_TTL_HOURS,
    INDIAN_NORAD_IDS,
    DEBRIS_GROUPS,
    MAX_DEBRIS_OBJECTS,
    CelesTrakError,
    RateLimitError,
    compute_tle_checksum,
    validate_tle_record,
    derive_orbital_parameters,
    parse_celestrak_tle_stream,
    fetch_with_retry,
    refresh_celestrak_data,
)

__all__ = [
    "CELESTRAK_GP_URL",
    "USER_AGENT",
    "DEFAULT_TIMEOUT",
    "CACHE_TTL_HOURS",
    "INDIAN_NORAD_IDS",
    "DEBRIS_GROUPS",
    "MAX_DEBRIS_OBJECTS",
    "CelesTrakError",
    "RateLimitError",
    "compute_tle_checksum",
    "validate_tle_record",
    "derive_orbital_parameters",
    "parse_celestrak_tle_stream",
    "fetch_with_retry",
    "refresh_celestrak_data",
]
