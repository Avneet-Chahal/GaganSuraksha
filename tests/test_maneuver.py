import math
import pytest
from services.maneuver import (
    STANDARD_GRAVITY,
    calculate_fuel_consumption_kg,
    calculate_separation_gain_km,
    validate_maneuver_parameters,
    plan_collision_avoidance_maneuver,
)
from backend.schemas.types import ManeuverRequest


def test_fuel_consumption_user_baseline():
    """
    Test requirement from prompt:
    'fuel for 0.38 m/s at 710 kg and Isp 220 s is about 0.125 kg.'
    """
    fuel = calculate_fuel_consumption_kg(
        spacecraft_mass_kg=710.0,
        isp_seconds=220.0,
        delta_v_ms=0.38,
    )
    # Tsiolkovsky gives 710 * (1 - exp(-0.38 / (9.80665 * 220))) = 0.125043... kg
    assert pytest.approx(fuel, abs=1e-3) == 0.125
    assert 0.124 <= fuel <= 0.126


def test_calculate_fuel_consumption_zero_dv():
    """Zero delta-v should consume zero propellant."""
    fuel = calculate_fuel_consumption_kg(spacecraft_mass_kg=1200.0, isp_seconds=290.0, delta_v_ms=0.0)
    assert fuel == 0.0


def test_calculate_fuel_consumption_known_tsiolkovsky_values():
    """Verifies Tsiolkovsky propellant calculation against analytical formula."""
    mass = 1000.0  # kg
    isp = 300.0    # s
    g0 = STANDARD_GRAVITY
    dv = 10.0      # m/s

    ve = g0 * isp
    expected_mass_ratio = math.exp(-dv / ve)
    expected_fuel = mass * (1.0 - expected_mass_ratio)

    actual_fuel = calculate_fuel_consumption_kg(mass, isp, dv)
    assert pytest.approx(actual_fuel, rel=1e-5) == expected_fuel
    assert actual_fuel > 0


def test_maneuver_parameter_validation():
    """Verifies that validate_maneuver_parameters rejects out-of-spec values."""
    # Valid parameters should pass without error
    validate_maneuver_parameters(delta_v_ms=0.5, spacecraft_mass_kg=710.0, isp_seconds=220.0)
    validate_maneuver_parameters(delta_v_ms=0.0, spacecraft_mass_kg=710.0, isp_seconds=220.0)
    validate_maneuver_parameters(delta_v_ms=5.0, spacecraft_mass_kg=710.0, isp_seconds=220.0)

    # Delta-v out of bounds (0.0 to 5.0 m/s)
    with pytest.raises(ValueError, match="Delta-V must be between 0.0 and 5.0 m/s"):
        validate_maneuver_parameters(delta_v_ms=-0.1, spacecraft_mass_kg=710.0, isp_seconds=220.0)

    with pytest.raises(ValueError, match="Delta-V must be between 0.0 and 5.0 m/s"):
        validate_maneuver_parameters(delta_v_ms=5.01, spacecraft_mass_kg=710.0, isp_seconds=220.0)

    # Spacecraft mass <= 0
    with pytest.raises(ValueError, match="Spacecraft wet mass must be greater than 0 kg"):
        validate_maneuver_parameters(delta_v_ms=1.0, spacecraft_mass_kg=0.0, isp_seconds=220.0)

    with pytest.raises(ValueError, match="Spacecraft wet mass must be greater than 0 kg"):
        validate_maneuver_parameters(delta_v_ms=1.0, spacecraft_mass_kg=-50.0, isp_seconds=220.0)

    # Isp <= 0
    with pytest.raises(ValueError, match="Specific impulse.*must be greater than 0 s"):
        validate_maneuver_parameters(delta_v_ms=1.0, spacecraft_mass_kg=710.0, isp_seconds=0.0)

    with pytest.raises(ValueError, match="Specific impulse.*must be greater than 0 s"):
        validate_maneuver_parameters(delta_v_ms=1.0, spacecraft_mass_kg=710.0, isp_seconds=-10.0)


def test_separation_gain_direction_and_lead_time():
    """
    Verifies that:
    1. 0.38 m/s PROGRADE at 12 h gives about 49 km gain (~49.25 km).
    2. dv = 0 gives zero gain.
    3. RADIAL and NORMAL give bounded epicycle gains that are much less than PROGRADE.
    4. In-track secular drift scales linearly with lead time (3 * dv * t).
    """
    # 1. 0.38 m/s PROGRADE at 12 h gives about 49 km gain
    gain_038_12h = calculate_separation_gain_km(delta_v_ms=0.38, direction="PROGRADE", lead_time_hours=12.0)
    assert pytest.approx(gain_038_12h, abs=0.5) == 49.25
    assert 48.5 <= gain_038_12h <= 49.5

    # 2. dv = 0 gives zero gain
    assert calculate_separation_gain_km(delta_v_ms=0.0, direction="PROGRADE", lead_time_hours=12.0) == 0.0
    assert calculate_separation_gain_km(delta_v_ms=0.0, direction="RADIAL_OUT", lead_time_hours=12.0) == 0.0
    assert calculate_separation_gain_km(delta_v_ms=0.0, direction="NORMAL", lead_time_hours=12.0) == 0.0

    # 3. RADIAL and NORMAL give much less than PROGRADE
    gain_radial = calculate_separation_gain_km(delta_v_ms=0.38, direction="RADIAL_OUT", lead_time_hours=12.0)
    gain_normal = calculate_separation_gain_km(delta_v_ms=0.38, direction="NORMAL", lead_time_hours=12.0)
    assert gain_radial < 1.0
    assert gain_normal < 1.0
    assert gain_radial < gain_038_12h / 50.0
    assert gain_normal < gain_038_12h / 50.0

    # 4. Lead time scaling: doubled lead time yields doubled in-track drift
    gain_038_24h = calculate_separation_gain_km(delta_v_ms=0.38, direction="PROGRADE", lead_time_hours=24.0)
    assert pytest.approx(gain_038_24h, rel=1e-5) == gain_038_12h * 2.0


def test_plan_maneuver_zero_dv_suboptimal():
    """A zero delta-V request retains current geometry and is marked SUBOPTIMAL."""
    req = ManeuverRequest(
        conjunction_id="CONJ-TEST",
        delta_v_ms=0.0,
        burn_time_utc="2026-10-10T12:00:00Z",
        direction="PROGRADE",
        spacecraft_mass_kg=1200.0,
        isp_seconds=280.0,
    )
    result = plan_collision_avoidance_maneuver(
        req=req,
        original_miss_distance_km=0.284,
        original_calibrated_probability=6.84e-4,
    )

    assert result.status == "SUBOPTIMAL"
    assert result.delta_v_ms == 0.0
    assert result.fuel_cost_kg == 0.0
    assert result.new_miss_distance_km == 0.284
    assert "No maneuver planned" in result.summary


def test_plan_maneuver_optimal_clearance():
    """A sufficient delta-V achieves > 2.0 km miss distance and Pc < 1e-5 (OPTIMAL)."""
    req = ManeuverRequest(
        conjunction_id="CONJ-TEST",
        delta_v_ms=0.05,  # 3 * 0.00005 * 43200 = 6.48 km gain
        burn_time_utc="2026-10-10T12:00:00Z",
        direction="PROGRADE",
        spacecraft_mass_kg=1200.0,
        isp_seconds=290.0,
    )
    result = plan_collision_avoidance_maneuver(
        req=req,
        original_miss_distance_km=0.284,
        original_calibrated_probability=6.84e-4,
        original_radial_km=0.10,
        original_in_track_km=0.25,
        original_cross_track_km=0.08,
    )

    assert result.status == "OPTIMAL"
    assert result.new_miss_distance_km >= 2.0
    assert result.new_probability < 1e-5
    assert result.fuel_cost_kg > 0.0
    assert "Optimal CAM" in result.summary


def test_plan_maneuver_acceptable_clearance():
    """A moderate delta-V reaches 1.0 km <= miss < 2.0 km (ACCEPTABLE)."""
    req = ManeuverRequest(
        conjunction_id="CONJ-TEST",
        delta_v_ms=0.01,  # 3 * 0.00001 * 43200 = 1.296 km gain -> new miss ~1.58 km
        burn_time_utc="2026-10-10T12:00:00Z",
        direction="PROGRADE",
        spacecraft_mass_kg=1200.0,
        isp_seconds=290.0,
    )
    result = plan_collision_avoidance_maneuver(
        req=req,
        original_miss_distance_km=0.284,
        original_calibrated_probability=6.84e-4,
        original_radial_km=0.10,
        original_in_track_km=0.25,
        original_cross_track_km=0.08,
    )

    assert result.status == "ACCEPTABLE"
    assert 1.0 <= result.new_miss_distance_km < 2.0
    assert result.new_probability < 1e-4
    assert "Acceptable CAM" in result.summary


def test_plan_maneuver_monotonic_risk_reduction():
    """Post-burn collision probability must strictly decrease with increasing delta-V."""
    req_low = ManeuverRequest(
        conjunction_id="CONJ-TEST",
        delta_v_ms=0.005,
        burn_time_utc="2026-10-10T12:00:00Z",
        direction="PROGRADE",
        spacecraft_mass_kg=710.0,
        isp_seconds=220.0,
    )
    req_high = ManeuverRequest(
        conjunction_id="CONJ-TEST",
        delta_v_ms=0.02,
        burn_time_utc="2026-10-10T12:00:00Z",
        direction="PROGRADE",
        spacecraft_mass_kg=710.0,
        isp_seconds=220.0,
    )
    res_low = plan_collision_avoidance_maneuver(
        req_low, 0.25, 5e-4,
        original_radial_km=0.10, original_in_track_km=0.20, original_cross_track_km=0.05
    )
    res_high = plan_collision_avoidance_maneuver(
        req_high, 0.25, 5e-4,
        original_radial_km=0.10, original_in_track_km=0.20, original_cross_track_km=0.05
    )

    assert res_high.new_miss_distance_km > res_low.new_miss_distance_km
    assert res_high.new_probability <= res_low.new_probability
    assert res_high.fuel_cost_kg > res_low.fuel_cost_kg


def test_maneuver_unknown_id_returns_404():
    """Verifies that POST /api/maneuver returns HTTP 404 when conjunction ID is unknown."""
    from fastapi.testclient import TestClient
    from backend.main import app

    with TestClient(app) as client:
        payload = {
            "conjunctionId": "CONJ-NONEXISTENT-UNKNOWN-9999",
            "deltaVMs": 0.38,
            "burnTimeUtc": "2026-10-10T12:00:00Z",
            "direction": "PROGRADE",
            "spacecraftMassKg": 710.0,
            "ispSeconds": 220.0,
        }
        res = client.post("/api/maneuver", json=payload)
        assert res.status_code == 404
        assert "not found" in res.json()["detail"].lower()
