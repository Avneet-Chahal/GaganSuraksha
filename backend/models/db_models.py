from typing import Optional
from sqlalchemy import (
    String,
    Integer,
    Float,
    Boolean,
    ForeignKey,
    Text,
    BigInteger,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.database import Base


class SatelliteModel(Base):
    __tablename__ = "satellites"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    norad_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    intl_designator: Mapped[str] = mapped_column(String(64))
    type: Mapped[str] = mapped_column(String(32), index=True)  # PAYLOAD, ROCKET_BODY, DEBRIS, UNKNOWN
    regime: Mapped[str] = mapped_column(String(16), index=True)  # LEO, MEO, GEO, HEO
    is_indian: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_watchlist: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    launch_date: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    owner_country: Mapped[str] = mapped_column(String(128))
    operator: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    apogee_km: Mapped[float] = mapped_column(Float)
    perigee_km: Mapped[float] = mapped_column(Float)
    altitude_km: Mapped[float] = mapped_column(Float)
    inclination_deg: Mapped[float] = mapped_column(Float)
    period_min: Mapped[float] = mapped_column(Float)
    velocity_km_s: Mapped[float] = mapped_column(Float)
    tle_epoch: Mapped[str] = mapped_column(String(64))
    tle_line1: Mapped[str] = mapped_column(Text)
    tle_line2: Mapped[str] = mapped_column(Text)
    data_source: Mapped[str] = mapped_column(String(32), default="SYNTHETIC")  # SYNTHETIC vs CELESTRAK


class ConjunctionModel(Base):
    __tablename__ = "conjunctions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    primary_sat_id: Mapped[str] = mapped_column(String(64), ForeignKey("satellites.id"), index=True)
    secondary_sat_id: Mapped[str] = mapped_column(String(64), ForeignKey("satellites.id"), index=True)
    tca_utc: Mapped[str] = mapped_column(String(64))
    tca_ms: Mapped[int] = mapped_column(BigInteger)
    miss_distance_km: Mapped[float] = mapped_column(Float)
    radial_miss_km: Mapped[float] = mapped_column(Float)
    in_track_miss_km: Mapped[float] = mapped_column(Float)
    cross_track_miss_km: Mapped[float] = mapped_column(Float)
    relative_velocity_km_s: Mapped[float] = mapped_column(Float)
    raw_probability: Mapped[float] = mapped_column(Float)
    calibrated_probability: Mapped[float] = mapped_column(Float)
    risk_level: Mapped[str] = mapped_column(String(16))  # NOMINAL, WARNING, CRITICAL

    # Covariance primary
    primary_radial_sigma_m: Mapped[float] = mapped_column(Float)
    primary_in_track_sigma_m: Mapped[float] = mapped_column(Float)
    primary_cross_track_sigma_m: Mapped[float] = mapped_column(Float)

    # Covariance secondary
    secondary_radial_sigma_m: Mapped[float] = mapped_column(Float)
    secondary_in_track_sigma_m: Mapped[float] = mapped_column(Float)
    secondary_cross_track_sigma_m: Mapped[float] = mapped_column(Float)

    recommended_action: Mapped[str] = mapped_column(String(32))
    recommended_delta_v_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    maneuver_fuel_cost_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    data_freshness_utc: Mapped[str] = mapped_column(String(64))
    data_quality_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ML-specific additive fields
    pc_raw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pc_ml: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pc_ml_calibrated: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ml_available: Mapped[bool] = mapped_column(Boolean, default=True)
    model_version: Mapped[Optional[str]] = mapped_column(String(32), default="v1.0.0", nullable=True)
    data_source: Mapped[str] = mapped_column(String(32), default="real")

    # Relationships
    primary_sat: Mapped["SatelliteModel"] = relationship("SatelliteModel", foreign_keys=[primary_sat_id], lazy="joined")
    secondary_sat: Mapped["SatelliteModel"] = relationship("SatelliteModel", foreign_keys=[secondary_sat_id], lazy="joined")


class DataSourceModel(Base):
    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    source: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16))  # ONLINE, DEGRADED, STANDBY
    last_updated_utc: Mapped[str] = mapped_column(String(64))
    latency_seconds: Mapped[int] = mapped_column(Integer)
    record_count: Mapped[int] = mapped_column(Integer)


class AnalyticsMetricModel(Base):
    __tablename__ = "analytics_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evaluation_period: Mapped[str] = mapped_column(String(128))
    total_conjunctions_monitored: Mapped[int] = mapped_column(Integer)
    unnecessary_maneuvers_avoided: Mapped[int] = mapped_column(Integer)
    fuel_saved_kg: Mapped[float] = mapped_column(Float)
    false_alarm_reduction_rate: Mapped[float] = mapped_column(Float)
    metrics_json: Mapped[str] = mapped_column(Text)  # JSON string for charts and detailed curves


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    norad_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    regime: Mapped[str] = mapped_column(String(16))  # LEO, MEO, GEO, HEO
    custom_pc_threshold: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    custom_miss_distance_km: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    added_at: Mapped[str] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AlertSettings(Base):
    __tablename__ = "alert_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    default_pc_threshold: Mapped[float] = mapped_column(Float, default=1.0e-4)
    default_miss_distance_km: Mapped[float] = mapped_column(Float, default=1.0)
    notify_email: Mapped[bool] = mapped_column(Boolean, default=False)
    email_address: Mapped[str] = mapped_column(String(256), default="")
    notify_telegram: Mapped[bool] = mapped_column(Boolean, default=False)
    telegram_chat_id: Mapped[str] = mapped_column(String(128), default="")
    notify_istrac_webhook: Mapped[bool] = mapped_column(Boolean, default=False)
    webhook_url: Mapped[str] = mapped_column(String(512), default="")


class SentAlert(Base):
    __tablename__ = "sent_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conjunction_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    sent_at_utc: Mapped[str] = mapped_column(String(64))
    channels_sent: Mapped[str] = mapped_column(String(128))


class IngestionStatusModel(Base):
    __tablename__ = "ingestion_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    source_name: Mapped[str] = mapped_column(String(128), default="CelesTrak GP API")
    last_fetch_utc: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    last_success_utc: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="STANDBY")  # ONLINE, DEGRADED, STANDBY
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    latency_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class BacktestTruthPair(Base):
    __tablename__ = "backtest_truth_pairs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    norad_id: Mapped[int] = mapped_column(Integer, index=True)
    satellite_name: Mapped[str] = mapped_column(String(128))
    epoch_a_utc: Mapped[str] = mapped_column(String(64))
    epoch_b_utc: Mapped[str] = mapped_column(String(64))
    horizon_hours: Mapped[float] = mapped_column(Float)
    baseline_3d_error_km: Mapped[float] = mapped_column(Float)
    corrected_3d_error_km: Mapped[float] = mapped_column(Float)
    improvement_pct: Mapped[float] = mapped_column(Float)
    recorded_at_utc: Mapped[str] = mapped_column(String(64))


