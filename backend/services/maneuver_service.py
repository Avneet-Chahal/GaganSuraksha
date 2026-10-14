"""Maneuver service proxying services.maneuver."""
from services.maneuver import (
    STANDARD_GRAVITY,
    calculate_fuel_consumption_kg,
    calculate_separation_gain_km,
    calculate_lead_time_hours,
    classify_maneuver_status,
    validate_maneuver_parameters,
    plan_collision_avoidance_maneuver,
)

__all__ = [
    "STANDARD_GRAVITY",
    "calculate_fuel_consumption_kg",
    "calculate_separation_gain_km",
    "calculate_lead_time_hours",
    "classify_maneuver_status",
    "validate_maneuver_parameters",
    "plan_collision_avoidance_maneuver",
]
