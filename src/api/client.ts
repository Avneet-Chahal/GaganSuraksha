import axios from 'axios';
import { useQuery } from '@tanstack/react-query';
import type {
  SatelliteRecord,
  TrajectoryResponse,
  ConjunctionEvent,
  ManeuverRequest,
  ManeuverResult,
  AnalyticsMetrics,
  DataSourceStatus,
  MlHealthStatus,
} from './types';
import {
  ALL_SATELLITES_CATALOG,
  CONJUNCTION_EVENTS,
  MOCK_ANALYTICS_METRICS,
  MOCK_DATA_SOURCES,
} from './mockData';
import { generateTrajectorySamples } from './sgp4Service';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 5000,
  headers: {
    'Content-Type': 'application/json',
  },
});

let demoDataActive = false;

export function getIsDemoMode(): boolean {
  return demoDataActive;
}

export function setIsDemoMode(val: boolean) {
  demoDataActive = val;
}

export async function fetchSatellites(): Promise<{ data: SatelliteRecord[]; isDemo: boolean }> {
  try {
    const res = await apiClient.get<SatelliteRecord[]>('/satellites');
    if (res.data && Array.isArray(res.data) && res.data.length > 0) {
      demoDataActive = false;
      return { data: res.data, isDemo: false };
    }
  } catch {
    // Offline fallback
  }
  demoDataActive = true;
  return { data: ALL_SATELLITES_CATALOG, isDemo: true };
}

export async function fetchTrajectories(
  satelliteIds: string[],
  startUtc: string,
  endUtc: string,
  stepSeconds = 120,
  corrected = false
): Promise<{ data: TrajectoryResponse[]; isDemo: boolean }> {
  try {
    const idsParam = satelliteIds.join(',');
    const res = await apiClient.get<TrajectoryResponse[]>('/trajectories', {
      params: {
        ids: idsParam,
        start: startUtc,
        end: endUtc,
        step: stepSeconds,
        corrected: corrected ? true : undefined,
      },
    });
    if (res.data && Array.isArray(res.data) && res.data.length > 0) {
      return { data: res.data, isDemo: false };
    }
  } catch {
    // Fallback to client-side SGP4
  }

  const startMs = new Date(startUtc).getTime();
  const endMs = new Date(endUtc).getTime();
  const results: TrajectoryResponse[] = [];

  for (const id of satelliteIds) {
    const sat = ALL_SATELLITES_CATALOG.find((s) => s.id === id);
    if (sat) {
      const points = generateTrajectorySamples(sat.tleLine1, sat.tleLine2, startMs, endMs, stepSeconds);
      results.push({
        satelliteId: id,
        stepSeconds,
        startTime: startUtc,
        endTime: endUtc,
        points,
      });
    }
  }

  return { data: results, isDemo: true };
}

export async function fetchConjunctions(): Promise<{ data: ConjunctionEvent[]; isDemo: boolean }> {
  try {
    const res = await apiClient.get<ConjunctionEvent[]>('/conjunctions');
    if (res.data && Array.isArray(res.data) && res.data.length > 0) {
      const isMock = res.data[0]?.dataSource === 'demo';
      demoDataActive = isMock;
      return { data: res.data, isDemo: isMock };
    }
  } catch {
    // Fallback to mock data
  }
  demoDataActive = true;
  return { data: CONJUNCTION_EVENTS, isDemo: true };
}

export async function fetchConjunctionById(id: string): Promise<{ data: ConjunctionEvent; isDemo: boolean }> {
  try {
    const res = await apiClient.get<ConjunctionEvent>(`/conjunctions/${id}`);
    if (res.data && res.data.id) {
      const isMock = res.data.dataSource === 'demo';
      return { data: res.data, isDemo: isMock };
    }
  } catch {
    // Fallback to mock event
  }
  const found = CONJUNCTION_EVENTS.find((c) => c.id === id) || CONJUNCTION_EVENTS[0];
  return { data: found, isDemo: true };
}

export async function planManeuver(req: ManeuverRequest): Promise<{ data: ManeuverResult; isDemo: boolean }> {
  try {
    const res = await apiClient.post<ManeuverResult>('/maneuver', req);
    if (res.data) {
      return { data: res.data, isDemo: false };
    }
  } catch {
    // Fallback
  }

  const conjunction = CONJUNCTION_EVENTS.find((c) => c.id === req.conjunctionId) || CONJUNCTION_EVENTS[0];
  const origMiss = conjunction.missDistanceKm;
  const origPc = conjunction.calibratedProbability;

  const dV = Math.max(0, req.deltaVMs);
  const separationGainKm = dV * 4.6;
  const newMiss = origMiss + separationGainKm;

  const g0 = 9.80665;
  const effectiveExhaustVelocity = g0 * req.ispSeconds;
  const massRatio = Math.exp(-dV / effectiveExhaustVelocity);
  const fuelCostKg = req.spacecraftMassKg * (1 - massRatio);

  const scale = origMiss / Math.max(0.01, newMiss);
  const newPc = origPc * Math.pow(scale, 3.5);

  const isOptimal = newMiss >= 2.0 && newPc < 1e-5;
  const isAcceptable = newMiss >= 1.0 && newPc < 1e-4;

  const result: ManeuverResult = {
    conjunctionId: req.conjunctionId,
    originalMissDistanceKm: origMiss,
    newMissDistanceKm: Number(newMiss.toFixed(3)),
    originalProbability: origPc,
    newProbability: Number(newPc.toExponential(3)),
    deltaVMs: dV,
    fuelCostKg: Number(fuelCostKg.toFixed(3)),
    status: isOptimal ? 'OPTIMAL' : isAcceptable ? 'ACCEPTABLE' : 'SUBOPTIMAL',
    recommendation: isOptimal || isAcceptable ? 'MANEUVER_RECOMMENDED' : 'WAIT_MONITOR',
    noNewConjunction: true,
    summary:
      dV === 0
        ? 'No maneuver planned. Current close approach geometry retained.'
        : isOptimal
        ? `Optimal CAM: ${dV.toFixed(2)} m/s achieves ${newMiss.toFixed(2)} km miss distance with Pc < 1e-5. Fuel cost: ${fuelCostKg.toFixed(2)} kg.`
        : `Acceptable CAM: achieves ${newMiss.toFixed(2)} km separation. Consider increasing delta-v for > 2.0 km margin.`,
    assumptions: {
      spacecraftMassKg: req.spacecraftMassKg,
      ispSeconds: req.ispSeconds,
      burnLeadTimeHours: 12,
    },
  };

  return { data: result, isDemo: true };
}

export async function fetchMetrics(): Promise<{ data: AnalyticsMetrics; isDemo: boolean }> {
  try {
    const res = await apiClient.get<AnalyticsMetrics>('/metrics');
    if (res.data) {
      const isMock = res.data.isDemo ?? res.data.dataSource === 'demo';
      return { data: res.data, isDemo: Boolean(isMock) };
    }
  } catch {
    // Fallback
  }
  return { data: MOCK_ANALYTICS_METRICS, isDemo: true };
}

export async function fetchMlHealth(): Promise<{ data: MlHealthStatus; isDemo: boolean }> {
  try {
    const res = await apiClient.get<MlHealthStatus>('/health/ml');
    if (res.data) {
      return { data: res.data, isDemo: false };
    }
  } catch {
    // Fallback
  }
  return {
    data: {
      status: 'ONLINE',
      modelVersion: 'v1.0.0',
      trainingDates: {
        trainStartUtc: '1986-02-22T01:49:50Z',
        trainEndUtc: '2003-11-15T21:37:44Z',
      },
      mlAvailable: true,
      referenceTruth: 'Later TLE epoch state (public TLE backtest)',
      dataSource: 'public TLE backtest',
    },
    isDemo: true,
  };
}

export async function fetchDataSources(): Promise<{ data: DataSourceStatus[]; isDemo: boolean }> {
  try {
    const res = await apiClient.get<DataSourceStatus[]>('/sources');
    if (res.data) {
      return { data: res.data, isDemo: false };
    }
  } catch {
    // Fallback
  }
  return { data: MOCK_DATA_SOURCES, isDemo: true };
}

// =====================================================================
// TanStack Query Hooks (quiet loading, error, and retry states)
// =====================================================================

export function useConjunctions() {
  return useQuery({
    queryKey: ['conjunctions'],
    queryFn: fetchConjunctions,
    refetchInterval: 30000,
    retry: 1,
    refetchOnWindowFocus: false,
  });
}

export function useConjunction(id: string | undefined) {
  return useQuery({
    queryKey: ['conjunction', id],
    queryFn: () => (id ? fetchConjunctionById(id) : Promise.reject(new Error('No ID'))),
    enabled: Boolean(id),
    retry: 1,
    refetchOnWindowFocus: false,
  });
}

export function useMetrics() {
  return useQuery({
    queryKey: ['metrics'],
    queryFn: fetchMetrics,
    retry: 1,
    refetchOnWindowFocus: false,
  });
}

export function useMlHealth() {
  return useQuery({
    queryKey: ['mlHealth'],
    queryFn: fetchMlHealth,
    retry: 1,
    refetchOnWindowFocus: false,
  });
}

export function useTrajectories(
  satelliteIds: string[],
  startUtc: string,
  endUtc: string,
  stepSeconds = 120,
  corrected = false
) {
  return useQuery({
    queryKey: ['trajectories', satelliteIds.join(','), startUtc, endUtc, stepSeconds, corrected],
    queryFn: () => fetchTrajectories(satelliteIds, startUtc, endUtc, stepSeconds, corrected),
    enabled: satelliteIds.length > 0,
    staleTime: 60000,
    retry: 1,
    refetchOnWindowFocus: false,
  });
}
