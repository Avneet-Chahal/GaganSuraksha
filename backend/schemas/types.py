from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

SatelliteType = Literal["PAYLOAD", "ROCKET_BODY", "DEBRIS", "UNKNOWN"]
OrbitRegime = Literal["LEO", "MEO", "GEO", "HEO"]
RiskLevel = Literal["NOMINAL", "WARNING", "CRITICAL"]
ManeuverDirection = Literal["PROGRADE", "RETROGRADE", "RADIAL_OUT", "RADIAL_IN", "NORMAL"]
ManeuverStatus = Literal["OPTIMAL", "ACCEPTABLE", "SUBOPTIMAL"]
RecommendedAction = Literal["WAIT_MONITOR", "MANEUVER_RECOMMENDED", "IMMEDIATE_ACTION"]
DataSourceState = Literal["ONLINE", "DEGRADED", "STANDBY"]


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class SatelliteRecord(CamelModel):
    id: str
    norad_id: int
    name: str
    intl_designator: str
    type: SatelliteType
    regime: OrbitRegime
    is_indian: bool
    is_watchlist: bool
    launch_date: Optional[str] = None
    owner_country: str
    operator: Optional[str] = None
    apogee_km: float
    perigee_km: float
    altitude_km: float
    inclination_deg: float
    period_min: float
    velocity_km_s: float
    tle_epoch: str
    tle_line1: str
    tle_line2: str
    data_source: Optional[str] = "SYNTHETIC"


class TrajectoryPoint(CamelModel):
    time_ms: int
    x: float
    y: float
    z: float
    vx: Optional[float] = None
    vy: Optional[float] = None
    vz: Optional[float] = None


class TrajectoryResponse(CamelModel):
    satellite_id: str
    step_seconds: int
    start_time: str
    end_time: str
    points: List[TrajectoryPoint]


class CovarianceMatrix(CamelModel):
    radial_sigma_m: float
    in_track_sigma_m: float
    cross_track_sigma_m: float


class ConjunctionEvent(CamelModel):
    id: str
    primary_sat: SatelliteRecord
    secondary_sat: SatelliteRecord
    tca_utc: str
    tca_ms: int
    miss_distance_km: float
    radial_miss_km: float
    in_track_miss_km: float
    cross_track_miss_km: float
    relative_velocity_km_s: float
    raw_probability: float
    calibrated_probability: float
    risk_level: RiskLevel
    primary_covariance: CovarianceMatrix
    secondary_covariance: CovarianceMatrix
    recommended_action: RecommendedAction
    recommended_delta_v_ms: Optional[float] = Field(
        default=None,
        serialization_alias="recommendedDeltaVMS",
        validation_alias="recommendedDeltaVMS",
    )
    maneuver_fuel_cost_kg: Optional[float] = None
    data_freshness_utc: str
    data_quality_note: Optional[str] = None
    # Additive ML fields
    pc_raw: Optional[float] = None
    pc_ml: Optional[float] = None
    pc_ml_calibrated: Optional[float] = None
    ml_available: bool = True
    model_version: Optional[str] = "v1.0.0"
    covariance: Optional[dict] = None
    data_source: Optional[str] = "real"


class ManeuverRequest(CamelModel):
    conjunction_id: str
    delta_v_ms: float = Field(..., ge=0.0, le=5.0)
    burn_time_utc: str
    direction: ManeuverDirection
    spacecraft_mass_kg: float = Field(..., gt=0.0)
    isp_seconds: float = Field(..., gt=0.0)


class ManeuverAssumptions(CamelModel):
    spacecraft_mass_kg: float
    isp_seconds: float
    burn_lead_time_hours: float


class ManeuverResult(CamelModel):
    conjunction_id: str
    original_miss_distance_km: float
    new_miss_distance_km: float
    original_probability: float
    new_probability: float
    delta_v_ms: float
    fuel_cost_kg: float
    status: ManeuverStatus
    summary: str
    assumptions: ManeuverAssumptions
    recommendation: Optional[str] = None
    no_new_conjunction: Optional[bool] = True


class DataSourceStatus(CamelModel):
    name: str
    source: str
    status: DataSourceState
    last_updated_utc: str
    latency_seconds: int
    record_count: int


class MonthlyFalseAlarm(CamelModel):
    month: str
    raw_count: int
    ml_corrected_count: int


class ReliabilityCurvePoint(CamelModel):
    forecast_bin: float
    observed_frequency_raw: float
    observed_frequency_ml: float
    ideal: float
    event_count: Optional[int] = None


class PositionErrorHorizonPoint(CamelModel):
    day_horizon: int
    sgp4_error_km: float
    ml_corrected_error_km: float
    sgp4_p10_km: Optional[float] = None
    sgp4_p90_km: Optional[float] = None
    ml_corrected_p10_km: Optional[float] = None
    ml_corrected_p90_km: Optional[float] = None


class AnalyticsMetrics(CamelModel):
    evaluation_period: str
    total_conjunctions_monitored: int
    unnecessary_maneuvers_avoided: int
    fuel_saved_kg: float
    false_alarm_reduction_rate: float
    false_alarms_by_month: List[MonthlyFalseAlarm]
    reliability_curve: List[ReliabilityCurvePoint]
    position_error_by_horizon: List[PositionErrorHorizonPoint]
    is_demo: Optional[bool] = False
    # Additive ML metrics fields
    error_by_horizon: Optional[List[Dict[str, Any]]] = None
    alerts_per_month: Optional[List[Dict[str, Any]]] = None
    missed_events: Optional[int] = 0
    reliability_bins: Optional[List[Dict[str, Any]]] = None
    reference_truth: Optional[str] = None
    date_range: Optional[str] = None
    data_source: Optional[str] = "real"



class WatchlistItemRecord(CamelModel):
    id: str
    norad_id: int
    name: str
    regime: OrbitRegime
    custom_pc_threshold: Optional[float] = None
    custom_miss_distance_km: Optional[float] = None
    added_at: str
    active: bool = True


class WatchlistItemCreate(CamelModel):
    norad_id: int
    name: str
    regime: OrbitRegime = "LEO"
    custom_pc_threshold: Optional[float] = None
    custom_miss_distance_km: Optional[float] = None
    active: bool = True


class AlertSettingsRecord(CamelModel):
    default_pc_threshold: float
    default_miss_distance_km: float
    notify_email: bool
    email_address: str
    notify_telegram: bool
    telegram_chat_id: str
    notify_istrac_webhook: bool
    webhook_url: str


class AlertSettingsUpdate(CamelModel):
    default_pc_threshold: Optional[float] = None
    default_miss_distance_km: Optional[float] = None
    notify_email: Optional[bool] = None
    email_address: Optional[str] = None
    notify_telegram: Optional[bool] = None
    telegram_chat_id: Optional[str] = None
    notify_istrac_webhook: Optional[bool] = None
    webhook_url: Optional[str] = None


AnalyticsMetrics.model_rebuild()

