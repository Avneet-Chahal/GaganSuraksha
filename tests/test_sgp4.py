import math
from datetime import datetime, timezone
from backend.services.sgp4_service import (
    parse_iso_datetime,
    generate_trajectory_samples,
    propagate_single_point,
    EARTH_RADIUS_KM,
)
from sgp4.api import Satrec

# CARTOSAT-2F realistic TLE
TLE_LINE1 = "1 43111U 18004A   26283.25833333  .00002154  00000+0  10425-3 0  9993"
TLE_LINE2 = "2 43111  97.5214 240.1142 0010412 112.5412 247.6214 15.20145212412854"


def test_parse_iso_datetime():
    """Verifies parsing of standard ISO-8601 strings with Z and timezone offsets."""
    dt1 = parse_iso_datetime("2026-10-10T12:00:00Z")
    assert dt1.year == 2026
    assert dt1.month == 10
    assert dt1.day == 10
    assert dt1.hour == 12
    assert dt1.tzinfo == timezone.utc

    dt2 = parse_iso_datetime("2026-10-10T14:30:00+00:00")
    assert dt2.hour == 14


def test_propagate_single_point_leo_bounds():
    """Verifies that propagating a LEO satellite produces physically realistic coordinates and speeds."""
    satrec = Satrec.twoline2rv(TLE_LINE1, TLE_LINE2)
    dt = datetime(2026, 10, 10, 12, 0, 0, tzinfo=timezone.utc)
    res = propagate_single_point(satrec, dt)

    assert res is not None
    x, y, z, vx, vy, vz = res

    # Position magnitude should be Earth radius + LEO altitude (~6800 - 6900 km)
    r_mag = math.sqrt(x * x + y * y + z * z)
    assert 6800.0 < r_mag < 7000.0

    # LEO orbital speed should be roughly 7.4 - 7.8 km/s
    v_mag = math.sqrt(vx * vx + vy * vy + vz * vz)
    assert 7.4 < v_mag < 7.8


def test_generate_trajectory_samples():
    """Generates a 30-minute window at 60s steps and verifies point spacing and counts."""
    start_iso = "2026-10-10T12:00:00Z"
    end_iso = "2026-10-10T12:30:00Z"
    step = 60

    trajectory = generate_trajectory_samples(
        satellite_id="43111",
        line1=TLE_LINE1,
        line2=TLE_LINE2,
        start_time_iso=start_iso,
        end_time_iso=end_iso,
        step_seconds=step,
    )

    assert trajectory.satellite_id == "43111"
    assert trajectory.step_seconds == 60
    assert len(trajectory.points) == 31  # 0 to 30 min inclusive = 31 points

    # Check timestamps step consecutively by 60,000 ms
    for i in range(len(trajectory.points) - 1):
        delta = trajectory.points[i + 1].time_ms - trajectory.points[i].time_ms
        assert delta == 60000
