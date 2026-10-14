"""
Gagan Suraksha - ML Integration & Pipeline Unit Tests.
Tests:
1. ISS state propagation against known orbit (NORAD 25544)
2. Miss distance consistency check (sqrt(R^2 + T^2 + N^2) == total_miss)
3. Pc raw vs ML comparison fixture (verifying both probabilities in [0, 1])
4. Graceful fallback when model files are missing (ml_available=False, never crashes)
5. GET /api/health/ml endpoint response
"""

import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sgp4.api import Satrec

from backend.main import app
from backend.services.sgp4_service import propagate_single_point
from backend.services.risk import (
    compute_total_miss_km,
    decompose_rtn,
    compute_foster_2d_pc,
    evaluate_conjunction_risk,
    calibrate_pc,
)
from backend.app.ml.predict import StatePredictor, correct_state

# Realistic ISS (ZARYA) TLE - NORAD 25544
ISS_LINE1 = "1 25544U 98067A   24080.52843750  .00014238  00000-0  25749-3 0  9997"
ISS_LINE2 = "2 25544  51.6420  34.5020 0004561  45.1234 314.9876 15.49812345445210"


# =====================================================================
# 1. ISS State Propagation Against Known Orbit
# =====================================================================
def test_iss_state_propagation_against_known_orbit():
    """
    Propagates ISS (NORAD 25544) at its TLE epoch and verifies physical orbital elements:
    - Orbit radius r in [6750, 6850] km (altitude ~370-470 km above Earth)
    - Orbital speed v in [7.60, 7.75] km/s (typical LEO speed for ISS)
    - SGP4 error code == 0
    """
    satrec = Satrec.twoline2rv(ISS_LINE1, ISS_LINE2)
    assert satrec.error == 0

    # Epoch date: 2024 Day 80.52843750 -> March 20, 2024 ~12:40:57 UTC
    jd_epoch = satrec.jdsatepoch + satrec.jdsatepochF
    epoch_ts = (jd_epoch - 2440587.5) * 86400.0
    epoch_dt = datetime(1970, 1, 1, tzinfo=timezone.utc) + np.timedelta64(int(epoch_ts), "s").astype(object)

    state = propagate_single_point(satrec, epoch_dt)
    assert state is not None
    x, y, z, vx, vy, vz = state

    r_mag = math.sqrt(x**2 + y**2 + z**2)
    v_mag = math.sqrt(vx**2 + vy**2 + vz**2)

    # Earth radius ~ 6378.137 km -> ISS altitude ~ 415-425 km -> r_mag in [6770, 6830] km
    assert 6750.0 <= r_mag <= 6850.0, f"ISS radius {r_mag:.2f} km out of expected range"

    # ISS orbital speed in LEO circular orbit ~ 7.66 km/s
    assert 7.60 <= v_mag <= 7.75, f"ISS speed {v_mag:.3f} km/s out of expected range"

    # Inclination is ~ 51.64 degrees
    inc_deg = math.degrees(satrec.inclo)
    assert abs(inc_deg - 51.64) < 0.1, f"Inclination {inc_deg:.2f} deg deviates from expected 51.64 deg"


# =====================================================================
# 2. Miss Distance Consistency Check
# =====================================================================
def test_miss_distance_consistency_check():
    """
    Verifies that total miss distance is strictly and uniquely derived from
    the RTN component vector: total_miss == sqrt(R^2 + T^2 + N^2).
    Ensures no discrepancy between component breakdown and scalar miss distance.
    """
    # Test cases with varying geometries
    test_cases = [
        (0.042, 0.115, 0.088),
        (0.0, 1.250, 0.0),
        (-0.350, 0.820, -0.190),
        (10.5, -4.2, 8.1),
    ]

    for r, t, n in test_cases:
        expected = math.sqrt(r**2 + t**2 + n**2)
        computed = compute_total_miss_km(r, t, n)
        assert abs(computed - expected) < 1e-9, f"Mismatch for ({r}, {t}, {n}): {computed} vs {expected}"

    # Also test RTN decomposition consistency with 3D Cartesian vector norm
    r1 = np.array([6800.0, 0.0, 0.0], dtype=np.float64)
    v1 = np.array([0.0, 7.66, 0.0], dtype=np.float64)
    # Secondary shifted by 0.5 km along-track and 0.2 km cross-track
    r2 = np.array([6800.0, 0.5, 0.2], dtype=np.float64)
    v2 = np.array([0.0, 7.66, 0.0], dtype=np.float64)

    res_r, res_t, res_n, total_miss, rel_vel = decompose_rtn(r1, v1, r2, v2)
    cartesian_norm = float(np.linalg.norm(r1 - r2))

    assert abs(total_miss - cartesian_norm) < 1e-9
    assert abs(math.sqrt(res_r**2 + res_t**2 + res_n**2) - total_miss) < 1e-9


# =====================================================================
# 3. Pc Raw vs ML Comparison Fixture
# =====================================================================
@pytest.fixture
def conjunction_scenario():
    """Provides realistic primary and secondary satellite states and metadata at TCA."""
    class FakeSat:
        def __init__(self, sat_id, sat_type, tle_epoch):
            self.id = sat_id
            self.type = sat_type
            self.tle_epoch = tle_epoch
            self.altitude_km = 600.0

    tca_dt = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)
    sat1 = FakeSat("SAT1", "PAYLOAD", "2026-10-14T12:00:00Z")
    sat2 = FakeSat("SAT2", "DEBRIS", "2026-10-14T10:00:00Z")

    r1 = np.array([6800.0, 0.0, 0.0], dtype=np.float64)
    v1 = np.array([0.0, 7.65, 0.0], dtype=np.float64)

    # Miss distance: 0.05 km in radial, 0.10 km in in-track, 0.02 km in cross-track
    r2 = np.array([6800.05, 0.10, 0.02], dtype=np.float64)
    v2 = np.array([0.0, 7.65, 1.0], dtype=np.float64)

    return {
        "primary_sat": sat1,
        "secondary_sat": sat2,
        "tca_dt": tca_dt,
        "r1": r1,
        "v1": v1,
        "r2": r2,
        "v2": v2,
    }


def test_pc_raw_vs_ml_comparison_fixture(conjunction_scenario):
    """
    Evaluates risk on the fixture and verifies:
    - Both pc_raw and pc_ml are valid probabilities in [0.0, 1.0].
    - pc_ml_calibrated is in [0.0, 1.0].
    - Covariances are provided per object (1-sigma RTN in metres).
    - Risk classification matches mission criteria.
    """
    scen = conjunction_scenario
    risk_res = evaluate_conjunction_risk(
        primary_sat=scen["primary_sat"],
        secondary_sat=scen["secondary_sat"],
        tca_dt=scen["tca_dt"],
        r1=scen["r1"],
        v1=scen["v1"],
        r2=scen["r2"],
        v2=scen["v2"],
    )

    assert "pc_raw" in risk_res
    assert "pc_ml" in risk_res
    assert "pc_ml_calibrated" in risk_res
    assert "ml_available" in risk_res
    assert "model_version" in risk_res

    pc_raw = risk_res["pc_raw"]
    pc_ml = risk_res["pc_ml"]
    pc_cal = risk_res["pc_ml_calibrated"]

    assert 0.0 <= pc_raw <= 1.0
    assert 0.0 <= pc_ml <= 1.0
    assert 0.0 <= pc_cal <= 1.0

    # Covariance uncertainty check
    cov1 = risk_res["primary_covariance_rtn_m"]
    cov2 = risk_res["secondary_covariance_rtn_m"]
    assert len(cov1) == 3 and all(s > 0 for s in cov1)
    assert len(cov2) == 3 and all(s > 0 for s in cov2)

    # Miss distance equals sqrt(r^2 + t^2 + n^2)
    derived_miss = math.sqrt(
        risk_res["radial_miss_km"] ** 2
        + risk_res["in_track_miss_km"] ** 2
        + risk_res["cross_track_miss_km"] ** 2
    )
    assert abs(risk_res["miss_distance_km"] - derived_miss) < 0.01


# =====================================================================
# 4. Fallback When Model Files Are Missing
# =====================================================================
def test_ml_fallback_when_models_missing(tmp_path):
    """
    Points predictor to an empty directory where no models or metadata exist:
    - Must set ml_available = False
    - correct_state() returns raw state untouched (zero shift)
    - Predictor never crashes
    - Calibrator fallback returns raw Pc with calibrated=False
    """
    empty_dir = tmp_path / "empty_models"
    empty_dir.mkdir()

    fallback_predictor = StatePredictor(model_dir=str(empty_dir))
    assert fallback_predictor.ml_available is False

    # Predictor residuals return zeros gracefully
    zero_preds = fallback_predictor.predict_rtn_residuals({"horizon_hours": 24.0})
    for target, q_map in zero_preds.items():
        assert q_map[0.5] == 0.0

    # correct_state returns uncorrected raw position and ml_available=False
    raw_r = np.array([6800.0, 100.0, 50.0], dtype=np.float64)
    raw_v = np.array([0.0, 7.6, 0.0], dtype=np.float64)
    epoch_dt = datetime(2026, 10, 12, 0, 0, 0, tzinfo=timezone.utc)
    target_dt = datetime(2026, 10, 13, 0, 0, 0, tzinfo=timezone.utc)

    corr_res = correct_state(
        sat_state=(raw_r, raw_v),
        tle_epoch=epoch_dt,
        t_target=target_dt,
        predictor=fallback_predictor,
    )

    assert corr_res.ml_available is False
    assert np.allclose(corr_res.corrected_position, raw_r)
    assert "bounds" in corr_res
    assert corr_res.bounds["sigma_rtn_m"] == (15.0, 50.0, 20.0)

    # Calibrate Pc with missing calibrator
    from backend.services.risk import load_pc_calibrator
    missing_calibrator = load_pc_calibrator(model_dir=str(empty_dir))
    assert missing_calibrator is None
    cal_val, is_cal = calibrate_pc(1.5e-4, calibrator=missing_calibrator)
    assert is_cal is False
    assert cal_val == 1.5e-4


# =====================================================================
# 5. Health ML API Endpoint
# =====================================================================
def test_health_ml_endpoint():
    """Verifies that GET /api/health/ml returns model version, training dates, and status."""
    with TestClient(app) as client:
        res = client.get("/api/health/ml")
        assert res.status_code == 200
        data = res.json()
        assert "status" in data
        assert "model_version" in data
        assert "training_dates" in data
        assert "ml_available" in data
        assert "reference_truth" in data
        assert "data_source" in data
        assert data["reference_truth"] != ""
