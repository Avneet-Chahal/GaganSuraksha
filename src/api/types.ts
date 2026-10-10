export type SatelliteType = 'PAYLOAD' | 'ROCKET_BODY' | 'DEBRIS' | 'UNKNOWN';
export type OrbitRegime = 'LEO' | 'MEO' | 'GEO' | 'HEO';
export type RiskLevel = 'NOMINAL' | 'WARNING' | 'CRITICAL';

export interface SatelliteRecord {
  id: string; // NORAD ID or catalog ID
  noradId: number;
  name: string;
  intlDesignator: string;
  type: SatelliteType;
  regime: OrbitRegime;
  isIndian: boolean;
  isWatchlist: boolean;
  launchDate?: string;
  ownerCountry: string; // e.g. "India (ISRO)", "CIS", "USA", "PRC"
  operator?: string;
  apogeeKm: number;
  perigeeKm: number;
  altitudeKm: number;
  inclinationDeg: number;
  periodMin: number;
  velocityKmS: number;
  tleEpoch: string; // ISO 8601 UTC
  tleLine1: string;
  tleLine2: string;
}

export interface TrajectoryPoint {
  timeMs: number; // UTC timestamp ms
  x: number; // ECI km
  y: number;
  z: number;
  vx?: number; // ECI km/s
  vy?: number;
  vz?: number;
}

export interface TrajectoryResponse {
  satelliteId: string;
  stepSeconds: number;
  startTime: string;
  endTime: string;
  points: TrajectoryPoint[];
}

export interface ConjunctionEvent {
  id: string;
  primarySat: SatelliteRecord;
  secondarySat: SatelliteRecord;
  tcaUtc: string; // Time of Closest Approach (ISO 8601 UTC)
  tcaMs: number; // UTC timestamp ms
  missDistanceKm: number; // Total miss distance
  radialMissKm: number;
  inTrackMissKm: number;
  crossTrackMissKm: number;
  relativeVelocityKmS: number;
  rawProbability: number; // Classical Foster 2D/3D Pc
  calibratedProbability: number; // ISRO NETRA ML-corrected Pc
  riskLevel: RiskLevel;
  primaryCovariance: {
    radialSigmaM: number;
    inTrackSigmaM: number;
    crossTrackSigmaM: number;
  };
  secondaryCovariance: {
    radialSigmaM: number;
    inTrackSigmaM: number;
    crossTrackSigmaM: number;
  };
  recommendedAction: 'WAIT_MONITOR' | 'MANEUVER_RECOMMENDED' | 'IMMEDIATE_ACTION';
  recommendedDeltaVMS?: number;
  maneuverFuelCostKg?: number;
  dataFreshnessUtc: string;
}

export interface ManeuverRequest {
  conjunctionId: string;
  deltaVMs: number; // m/s
  burnTimeUtc: string;
  direction: 'PROGRADE' | 'RETROGRADE' | 'RADIAL_OUT' | 'RADIAL_IN' | 'NORMAL';
  spacecraftMassKg: number;
  ispSeconds: number;
}

export interface ManeuverResult {
  conjunctionId: string;
  originalMissDistanceKm: number;
  newMissDistanceKm: number;
  originalProbability: number;
  newProbability: number;
  deltaVMs: number;
  fuelCostKg: number;
  status: 'OPTIMAL' | 'ACCEPTABLE' | 'SUBOPTIMAL';
  summary: string;
  assumptions: {
    spacecraftMassKg: number;
    ispSeconds: number;
    burnLeadTimeHours: number;
  };
}

export interface AnalyticsMetrics {
  evaluationPeriod: string;
  totalConjunctionsMonitored: number;
  unnecessaryManeuversAvoided: number;
  fuelSavedKg: number;
  falseAlarmReductionRate: number; // e.g. 0.42 = 42%
  falseAlarmsByMonth: {
    month: string;
    rawCount: number;
    mlCorrectedCount: number;
  }[];
  reliabilityCurve: {
    forecastBin: number; // Predicted probability (0.0 to 1.0)
    observedFrequencyRaw: number;
    observedFrequencyMl: number;
    ideal: number;
  }[];
  positionErrorByHorizon: {
    dayHorizon: number; // 1 to 7 days
    sgp4ErrorKm: number;
    mlCorrectedErrorKm: number;
  }[];
}

export interface WatchlistSatelliteSetting {
  id: string;
  noradId: number;
  name: string;
  regime: OrbitRegime;
  customPcThreshold?: number;
  customMissDistanceKm?: number;
  addedAt: string;
  active: boolean;
}

export interface AlertThresholdSettings {
  defaultPcThreshold: number; // e.g. 1e-4
  defaultMissDistanceKm: number; // e.g. 1.0
  notifyEmail: boolean;
  emailAddress: string;
  notifyTelegram: boolean;
  telegramChatId: string;
  notifyIstracWebhook: boolean;
  webhookUrl: string;
}

export interface DataSourceStatus {
  name: string;
  source: string;
  status: 'ONLINE' | 'DEGRADED' | 'STANDBY';
  lastUpdatedUtc: string;
  latencySeconds: number;
  recordCount: number;
}
