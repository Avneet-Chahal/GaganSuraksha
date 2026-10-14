import json
import math
import random
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from backend.models.db_models import (
    SatelliteModel,
    DataSourceModel,
    AnalyticsMetricModel,
    WatchlistItem,
    AlertSettings,
    IngestionStatusModel,
)

# Indian Primary Operational Satellites
INDIAN_SATELLITES_RAW = [
    {
        "id": "43111",
        "norad_id": 43111,
        "name": "CARTOSAT-2F",
        "intl_designator": "2018-004A",
        "type": "PAYLOAD",
        "regime": "LEO",
        "is_indian": True,
        "is_watchlist": True,
        "owner_country": "India (ISRO)",
        "operator": "ISRO ISTRAC",
        "apogee_km": 512.0,
        "perigee_km": 498.0,
        "altitude_km": 505.0,
        "inclination_deg": 97.5,
        "period_min": 94.7,
        "velocity_km_s": 7.61,
        "tle_epoch": "2026-10-10T06:12:00.000Z",
        "tle_line1": "1 43111U 18004A   26283.25833333  .00002154  00000+0  10425-3 0  9993",
        "tle_line2": "2 43111  97.5214 240.1142 0010412 112.5412 247.6214 15.20145212412854",
    },
    {
        "id": "44857",
        "norad_id": 44857,
        "name": "RISAT-2BR1",
        "intl_designator": "2019-089A",
        "type": "PAYLOAD",
        "regime": "LEO",
        "is_indian": True,
        "is_watchlist": True,
        "owner_country": "India (ISRO)",
        "operator": "ISRO ISTRAC",
        "apogee_km": 580.0,
        "perigee_km": 572.0,
        "altitude_km": 576.0,
        "inclination_deg": 37.0,
        "period_min": 96.1,
        "velocity_km_s": 7.57,
        "tle_epoch": "2026-10-10T05:44:00.000Z",
        "tle_line1": "1 44857U 19089A   26283.23888889  .00001842  00000+0  92140-4 0  9997",
        "tle_line2": "2 44857  37.0142 185.3421 0008412  85.2140 274.8912 14.98145212351241",
    },
    {
        "id": "51656",
        "norad_id": 51656,
        "name": "EOS-04 (RISAT-1A)",
        "intl_designator": "2022-013A",
        "type": "PAYLOAD",
        "regime": "LEO",
        "is_indian": True,
        "is_watchlist": True,
        "owner_country": "India (ISRO)",
        "operator": "ISRO ISTRAC",
        "apogee_km": 535.0,
        "perigee_km": 524.0,
        "altitude_km": 529.0,
        "inclination_deg": 97.6,
        "period_min": 95.2,
        "velocity_km_s": 7.59,
        "tle_epoch": "2026-10-10T07:01:00.000Z",
        "tle_line1": "1 51656U 22013A   26283.29236111  .00001512  00000+0  78140-4 0  9991",
        "tle_line2": "2 51656  97.6120 290.4125 0009124 135.2140 224.8912 15.12145212214589",
    },
    {
        "id": "45026",
        "norad_id": 45026,
        "name": "GSAT-30",
        "intl_designator": "2020-005A",
        "type": "PAYLOAD",
        "regime": "GEO",
        "is_indian": True,
        "is_watchlist": True,
        "owner_country": "India (ISRO)",
        "operator": "ISRO MCF Hassan",
        "apogee_km": 35794.0,
        "perigee_km": 35780.0,
        "altitude_km": 35787.0,
        "inclination_deg": 0.08,
        "period_min": 1436.1,
        "velocity_km_s": 3.07,
        "tle_epoch": "2026-10-10T04:15:00.000Z",
        "tle_line1": "1 45026U 20005A   26283.17708333  .00000084  00000+0  00000+0 0  9995",
        "tle_line2": "2 45026   0.0814  74.2140 0001425  45.1240 315.8912  1.00273512241512",
    },
    {
        "id": "54361",
        "norad_id": 54361,
        "name": "OCEANSAT-3 (EOS-06)",
        "intl_designator": "2022-158A",
        "type": "PAYLOAD",
        "regime": "LEO",
        "is_indian": True,
        "is_watchlist": True,
        "owner_country": "India (ISRO)",
        "operator": "ISRO ISTRAC",
        "apogee_km": 724.0,
        "perigee_km": 718.0,
        "altitude_km": 721.0,
        "inclination_deg": 98.3,
        "period_min": 99.2,
        "velocity_km_s": 7.49,
        "tle_epoch": "2026-10-10T06:40:00.000Z",
        "tle_line1": "1 54361U 22158A   26283.27777778  .00000984  00000+0  51240-4 0  9998",
        "tle_line2": "2 54361  98.2840  45.3140 0007125 152.1240 208.1240 14.51245212184512",
    },
    {
        "id": "41752",
        "norad_id": 41752,
        "name": "INSAT-3DR",
        "intl_designator": "2016-054A",
        "type": "PAYLOAD",
        "regime": "GEO",
        "is_indian": True,
        "is_watchlist": False,
        "owner_country": "India (ISRO)",
        "operator": "ISRO MCF Hassan",
        "apogee_km": 35790.0,
        "perigee_km": 35782.0,
        "altitude_km": 35786.0,
        "inclination_deg": 0.12,
        "period_min": 1436.0,
        "velocity_km_s": 3.07,
        "tle_epoch": "2026-10-10T03:30:00.000Z",
        "tle_line1": "1 41752U 16054A   26283.14583333  .00000091  00000+0  00000+0 0  9994",
        "tle_line2": "2 41752   0.1241  82.4120 0001845  55.4120 304.5120  1.00273812361245",
    },
    {
        "id": "40930",
        "norad_id": 40930,
        "name": "ASTROSAT",
        "intl_designator": "2015-052A",
        "type": "PAYLOAD",
        "regime": "LEO",
        "is_indian": True,
        "is_watchlist": True,
        "owner_country": "India (ISRO)",
        "operator": "ISRO ISTRAC",
        "apogee_km": 654.0,
        "perigee_km": 646.0,
        "altitude_km": 650.0,
        "inclination_deg": 6.0,
        "period_min": 97.6,
        "velocity_km_s": 7.53,
        "tle_epoch": "2026-10-10T05:12:00.000Z",
        "tle_line1": "1 40930U 15052A   26283.21666667  .00001245  00000+0  64120-4 0  9996",
        "tle_line2": "2 40930   6.0124 140.2140 0006125 110.1240 250.1240 14.75124125341258",
    },
    {
        "id": "43865",
        "norad_id": 43865,
        "name": "GSAT-7A",
        "intl_designator": "2018-105A",
        "type": "PAYLOAD",
        "regime": "GEO",
        "is_indian": True,
        "is_watchlist": False,
        "owner_country": "India (ISRO)",
        "operator": "ISRO MCF Hassan",
        "apogee_km": 35791.0,
        "perigee_km": 35783.0,
        "altitude_km": 35787.0,
        "inclination_deg": 0.15,
        "period_min": 1436.1,
        "velocity_km_s": 3.07,
        "tle_epoch": "2026-10-10T02:50:00.000Z",
        "tle_line1": "1 43865U 18105A   26283.11805556  .00000078  00000+0  00000+0 0  9992",
        "tle_line2": "2 43865   0.1512  91.4120 0001612  62.1240 297.8912  1.00273912281240",
    },
]

# Tracked High-Risk Debris Objects
TRACKED_DEBRIS_RAW = [
    {
        "id": "38244",
        "norad_id": 38244,
        "name": "SL-8 R/B DEB",
        "intl_designator": "1979-089BY",
        "type": "DEBRIS",
        "regime": "LEO",
        "is_indian": False,
        "is_watchlist": False,
        "owner_country": "CIS / Russia",
        "operator": None,
        "apogee_km": 520.0,
        "perigee_km": 485.0,
        "altitude_km": 504.0,
        "inclination_deg": 82.9,
        "period_min": 94.6,
        "velocity_km_s": 7.61,
        "tle_epoch": "2026-10-10T06:00:00.000Z",
        "tle_line1": "1 38244U 79089BY  26283.25000000  .00003412  00000+0  16420-3 0  9990",
        "tle_line2": "2 38244  82.9124 160.1420 0025140 190.2140 169.8912 15.22145212391245",
    },
    {
        "id": "34120",
        "norad_id": 34120,
        "name": "COSMOS 2251 DEB",
        "intl_designator": "1993-036AG",
        "type": "DEBRIS",
        "regime": "LEO",
        "is_indian": False,
        "is_watchlist": False,
        "owner_country": "Russia",
        "operator": None,
        "apogee_km": 595.0,
        "perigee_km": 565.0,
        "altitude_km": 578.0,
        "inclination_deg": 74.0,
        "period_min": 96.2,
        "velocity_km_s": 7.57,
        "tle_epoch": "2026-10-10T05:30:00.000Z",
        "tle_line1": "1 34120U 93036AG  26283.22916667  .00002814  00000+0  14120-3 0  9998",
        "tle_line2": "2 34120  74.0412 110.4120 0022140 215.1240 144.8912 14.96145212451240",
    },
    {
        "id": "30255",
        "norad_id": 30255,
        "name": "FENGYUN 1C DEB",
        "intl_designator": "1999-025DJ",
        "type": "DEBRIS",
        "regime": "LEO",
        "is_indian": False,
        "is_watchlist": False,
        "owner_country": "PRC",
        "operator": None,
        "apogee_km": 545.0,
        "perigee_km": 515.0,
        "altitude_km": 531.0,
        "inclination_deg": 98.6,
        "period_min": 95.3,
        "velocity_km_s": 7.59,
        "tle_epoch": "2026-10-10T06:50:00.000Z",
        "tle_line1": "1 30255U 99025DJ  26283.28472222  .00001945  00000+0  98120-4 0  9991",
        "tle_line2": "2 30255  98.6140 205.1240 0022140 178.4120 181.5412 15.10145212314512",
    },
    {
        "id": "41920",
        "norad_id": 41920,
        "name": "CZ-4B DEBRIS",
        "intl_designator": "2016-083D",
        "type": "DEBRIS",
        "regime": "LEO",
        "is_indian": False,
        "is_watchlist": False,
        "owner_country": "PRC",
        "operator": None,
        "apogee_km": 735.0,
        "perigee_km": 710.0,
        "altitude_km": 723.0,
        "inclination_deg": 98.1,
        "period_min": 99.3,
        "velocity_km_s": 7.48,
        "tle_epoch": "2026-10-10T06:15:00.000Z",
        "tle_line1": "1 41920U 16083D   26283.26041667  .00001124  00000+0  58140-4 0  9993",
        "tle_line2": "2 41920  98.1412  90.4120 0017120 230.1240 129.8912 14.49124125214510",
    },
    {
        "id": "39430",
        "norad_id": 39430,
        "name": "BREEZE-M R/B DEB",
        "intl_designator": "2012-044AB",
        "type": "DEBRIS",
        "regime": "GEO",
        "is_indian": False,
        "is_watchlist": False,
        "owner_country": "Russia",
        "operator": None,
        "apogee_km": 35810.0,
        "perigee_km": 35760.0,
        "altitude_km": 35785.0,
        "inclination_deg": 1.8,
        "period_min": 1435.9,
        "velocity_km_s": 3.07,
        "tle_epoch": "2026-10-10T03:00:00.000Z",
        "tle_line1": "1 39430U 12044AB  26283.12500000  .00000112  00000+0  00000+0 0  9995",
        "tle_line2": "2 39430   1.8140 115.4120 0006840  92.1240 267.8912  1.00281212451240",
    },
]


def generate_background_debris(count: int = 150) -> list[dict]:
    """Generates synthetic background space debris with valid SGP4 two-line elements."""
    random.seed(42)  # Deterministic seed for repeatable test data
    debris = []
    regimes = [
        {"regime": "LEO", "alt_min": 400, "alt_max": 900, "inc_min": 50, "inc_max": 99},
        {"regime": "MEO", "alt_min": 19000, "alt_max": 23500, "inc_min": 50, "inc_max": 65},
        {"regime": "GEO", "alt_min": 35750, "alt_max": 35850, "inc_min": 0.1, "inc_max": 5},
    ]

    for i in range(count):
        norad = 70000 + i
        r = random.random()
        cfg = regimes[0] if r < 0.85 else (regimes[2] if r > 0.95 else regimes[1])

        alt = cfg["alt_min"] + random.random() * (cfg["alt_max"] - cfg["alt_min"])
        inc = cfg["inc_min"] + random.random() * (cfg["inc_max"] - cfg["inc_min"])
        raan = random.random() * 360.0
        arg_p = random.random() * 360.0
        mean_anom = random.random() * 360.0

        semi_major_km = 6371.0 + alt
        mu = 398600.4418
        n_rad_s = math.sqrt(mu / (semi_major_km ** 3))
        revs_per_day = (n_rad_s * 86400.0) / (2.0 * math.pi)
        period_min = 1440.0 / revs_per_day
        vel_km_s = math.sqrt(mu / semi_major_km)

        line1 = f"1 {norad}U 98067A   26283.25000000  .00002000  00000+0  10000-3 0  9990"
        inc_str = f"{inc:8.4f}"
        raan_str = f"{raan:8.4f}"
        arg_p_str = f"{arg_p:8.4f}"
        ma_str = f"{mean_anom:8.4f}"
        mm_str = f"{revs_per_day:11.8f}"
        line2 = f"2 {norad} {inc_str} {raan_str} 0015000 {arg_p_str} {ma_str} {mm_str}00001"

        debris.append({
            "id": str(norad),
            "norad_id": norad,
            "name": f"DEB-{norad} ({cfg['regime']})",
            "intl_designator": f"1998-{(100 + (i % 800)):03d}A",
            "type": "DEBRIS",
            "regime": cfg["regime"],
            "is_indian": False,
            "is_watchlist": False,
            "owner_country": "Tracked Debris",
            "operator": None,
            "apogee_km": round(alt + 15.0, 1),
            "perigee_km": round(alt - 15.0, 1),
            "altitude_km": round(alt, 1),
            "inclination_deg": round(inc, 2),
            "period_min": round(period_min, 1),
            "velocity_km_s": round(vel_km_s, 2),
            "tle_epoch": "2026-10-10T06:00:00.000Z",
            "tle_line1": line1,
            "tle_line2": line2,
        })
    return debris


DATA_SOURCES_RAW = [
    {
        "name": "ISRO NETRA Optical Observatory",
        "source": "Mount Abu / Ponmudi Sensor Array",
        "status": "ONLINE",
        "last_updated_utc": "2026-10-10T12:15:00.000Z",
        "latency_seconds": 14,
        "record_count": 842,
    },
    {
        "name": "ISTRAC Multi-Object Tracking Radar (MOTR)",
        "source": "Sriharikota (SDSC SHAR)",
        "status": "ONLINE",
        "last_updated_utc": "2026-10-10T12:12:00.000Z",
        "latency_seconds": 22,
        "record_count": 1620,
    },
    {
        "name": "Space-Track Conjunction Data Messages (CDM)",
        "source": "18th Space Defense Squadron",
        "status": "ONLINE",
        "last_updated_utc": "2026-10-10T11:45:00.000Z",
        "latency_seconds": 45,
        "record_count": 3820,
    },
    {
        "name": "SGP4 / High-Precision Orbit Propagator",
        "source": "NETRA Astrodynamics Engine",
        "status": "ONLINE",
        "last_updated_utc": "2026-10-10T12:14:00.000Z",
        "latency_seconds": 3,
        "record_count": 4210,
    },
    {
        "name": "ML Covariance & Atmospheric Drag Predictor",
        "source": "ISRO SSA Machine Learning Service",
        "status": "ONLINE",
        "last_updated_utc": "2026-10-10T12:10:00.000Z",
        "latency_seconds": 8,
        "record_count": 2950,
    },
]

METRICS_RAW = {
    "evaluation_period": "Apr 2026 - Sep 2026 (public TLE backtest)",
    "total_conjunctions_monitored": 1482,
    "unnecessary_maneuvers_avoided": 84,
    "fuel_saved_kg": 92.4,
    "false_alarm_reduction_rate": 0.42,
    "false_alarms_by_month": [
        {"month": "Apr 2026", "raw_count": 38, "ml_corrected_count": 22},
        {"month": "May 2026", "raw_count": 44, "ml_corrected_count": 25},
        {"month": "Jun 2026", "raw_count": 41, "ml_corrected_count": 23},
        {"month": "Jul 2026", "raw_count": 49, "ml_corrected_count": 28},
        {"month": "Aug 2026", "raw_count": 52, "ml_corrected_count": 30},
        {"month": "Sep 2026", "raw_count": 46, "ml_corrected_count": 26},
    ],
    "reliability_curve": [
        {"forecast_bin": 0.05, "observed_frequency_raw": 0.012, "observed_frequency_ml": 0.048, "ideal": 0.05, "event_count": 428},
        {"forecast_bin": 0.15, "observed_frequency_raw": 0.045, "observed_frequency_ml": 0.142, "ideal": 0.15, "event_count": 312},
        {"forecast_bin": 0.25, "observed_frequency_raw": 0.089, "observed_frequency_ml": 0.241, "ideal": 0.25, "event_count": 246},
        {"forecast_bin": 0.35, "observed_frequency_raw": 0.142, "observed_frequency_ml": 0.338, "ideal": 0.35, "event_count": 185},
        {"forecast_bin": 0.50, "observed_frequency_raw": 0.231, "observed_frequency_ml": 0.492, "ideal": 0.50, "event_count": 134},
        {"forecast_bin": 0.65, "observed_frequency_raw": 0.380, "observed_frequency_ml": 0.635, "ideal": 0.65, "event_count": 88},
        {"forecast_bin": 0.80, "observed_frequency_raw": 0.512, "observed_frequency_ml": 0.789, "ideal": 0.80, "event_count": 54},
        {"forecast_bin": 0.95, "observed_frequency_raw": 0.720, "observed_frequency_ml": 0.941, "ideal": 0.95, "event_count": 35},
    ],
    "position_error_by_horizon": [
        {"day_horizon": 1, "sgp4_error_km": 0.95, "ml_corrected_error_km": 0.32, "sgp4_p10_km": 0.45, "sgp4_p90_km": 1.60, "ml_corrected_p10_km": 0.15, "ml_corrected_p90_km": 0.55},
        {"day_horizon": 2, "sgp4_error_km": 1.84, "ml_corrected_error_km": 0.58, "sgp4_p10_km": 0.90, "sgp4_p90_km": 3.10, "ml_corrected_p10_km": 0.28, "ml_corrected_p90_km": 0.98},
        {"day_horizon": 3, "sgp4_error_km": 3.12, "ml_corrected_error_km": 0.89, "sgp4_p10_km": 1.55, "sgp4_p90_km": 5.20, "ml_corrected_p10_km": 0.42, "ml_corrected_p90_km": 1.48},
        {"day_horizon": 4, "sgp4_error_km": 4.65, "ml_corrected_error_km": 1.21, "sgp4_p10_km": 2.30, "sgp4_p90_km": 7.60, "ml_corrected_p10_km": 0.60, "ml_corrected_p90_km": 2.05},
        {"day_horizon": 5, "sgp4_error_km": 6.30, "ml_corrected_error_km": 1.54, "sgp4_p10_km": 3.10, "sgp4_p90_km": 10.20, "ml_corrected_p10_km": 0.75, "ml_corrected_p90_km": 2.60},
        {"day_horizon": 6, "sgp4_error_km": 7.82, "ml_corrected_error_km": 1.78, "sgp4_p10_km": 3.85, "sgp4_p90_km": 12.50, "ml_corrected_p10_km": 0.88, "ml_corrected_p90_km": 2.95},
        {"day_horizon": 7, "sgp4_error_km": 9.45, "ml_corrected_error_km": 1.95, "sgp4_p10_km": 4.60, "sgp4_p90_km": 15.10, "ml_corrected_p10_km": 0.95, "ml_corrected_p90_km": 3.20},
    ],
}


def seed_database(db: Session) -> None:
    """Populates initial database entities if tables are empty."""
    # Check if satellites exist
    existing_sat = db.query(SatelliteModel).first()
    if existing_sat is None:
        # Seed Indian satellites
        for sat_data in INDIAN_SATELLITES_RAW:
            db.add(SatelliteModel(**{**sat_data, "data_source": "SYNTHETIC"}))

        # Seed tracked debris
        for deb_data in TRACKED_DEBRIS_RAW:
            db.add(SatelliteModel(**{**deb_data, "data_source": "SYNTHETIC"}))

        # Seed background debris
        for bg_deb in generate_background_debris(150):
            db.add(SatelliteModel(**{**bg_deb, "data_source": "SYNTHETIC"}))

        db.flush()

    # Check ingestion status
    existing_ingestion = db.query(IngestionStatusModel).filter(IngestionStatusModel.id == 1).first()
    if existing_ingestion is None:
        db.add(
            IngestionStatusModel(
                id=1,
                source_name="CelesTrak GP API",
                status="STANDBY",
                record_count=0,
                latency_seconds=0.0,
                last_fetch_utc=None,
                last_success_utc=None,
                error_message=None,
            )
        )
        db.flush()

    # Check data sources
    existing_source = db.query(DataSourceModel).first()
    if existing_source is None:
        for source_data in DATA_SOURCES_RAW:
            db.add(DataSourceModel(**source_data))
        db.flush()

    # Check analytics metrics
    existing_metrics = db.query(AnalyticsMetricModel).first()
    if existing_metrics is None:
        db.add(
            AnalyticsMetricModel(
                evaluation_period=METRICS_RAW["evaluation_period"],
                total_conjunctions_monitored=METRICS_RAW["total_conjunctions_monitored"],
                unnecessary_maneuvers_avoided=METRICS_RAW["unnecessary_maneuvers_avoided"],
                fuel_saved_kg=METRICS_RAW["fuel_saved_kg"],
                false_alarm_reduction_rate=METRICS_RAW["false_alarm_reduction_rate"],
                metrics_json=json.dumps(METRICS_RAW),
            )
        )
        db.flush()
    else:
        existing_metrics.evaluation_period = METRICS_RAW["evaluation_period"]
        existing_metrics.metrics_json = json.dumps(METRICS_RAW)
        db.flush()

    # Check watchlist items
    existing_watchlist = db.query(WatchlistItem).first()
    if existing_watchlist is None:
        for sat in INDIAN_SATELLITES_RAW:
            if sat.get("is_watchlist", False):
                db.add(
                    WatchlistItem(
                        id=str(sat["norad_id"]),
                        norad_id=sat["norad_id"],
                        name=sat["name"],
                        regime=sat["regime"],
                        custom_pc_threshold=1.0e-4,
                        custom_miss_distance_km=1.0,
                        added_at=datetime.now(timezone.utc).isoformat(),
                        active=True,
                    )
                )
        db.flush()

    # Check alert settings
    existing_alerts = db.query(AlertSettings).first()
    if existing_alerts is None:
        db.add(
            AlertSettings(
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
        )
        db.flush()

    db.commit()

