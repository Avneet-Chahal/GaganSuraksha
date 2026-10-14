import * as satellite from 'satellite.js';
import type { TrajectoryPoint } from './types';

export const EARTH_RADIUS_KM = 6371.0;
export const SCENE_EARTH_RADIUS = 2.0;
export const KM_TO_SCENE_SCALE = SCENE_EARTH_RADIUS / EARTH_RADIUS_KM;

// Module-level cache for parsed TLE SatRec objects
const satrecCache = new Map<string, satellite.SatRec>();

export function getCachedSatrec(line1: string, line2: string): satellite.SatRec {
  const key = `${line1.trim()}|${line2.trim()}`;
  let satrec = satrecCache.get(key);
  if (!satrec) {
    satrec = satellite.twoline2satrec(line1.trim(), line2.trim());
    satrecCache.set(key, satrec);
  }
  return satrec;
}

/**
 * Converts ECI coordinates in km to 3D Scene space coordinates.
 */
export function eciKmToSceneCoords(xKm: number, yKm: number, zKm: number): [number, number, number] {
  return [
    xKm * KM_TO_SCENE_SCALE,
    zKm * KM_TO_SCENE_SCALE, // celestial north is up
    -yKm * KM_TO_SCENE_SCALE,
  ];
}

/**
 * Calculates Greenwich Mean Sidereal Time (GMST) in radians for the specified UTC date/ms.
 */
export function getGmstRadians(dateOrMs: Date | number): number {
  const date = typeof dateOrMs === 'number' ? new Date(dateOrMs) : dateOrMs;
  return satellite.gstime(date);
}

/**
 * Propagate a satellite from TLE lines at a specific UTC timestamp.
 */
export function propagateTleAtTime(
  line1: string,
  line2: string,
  timeMs: number
): { x: number; y: number; z: number; vx: number; vy: number; vz: number; altitudeKm: number } | null {
  try {
    const satrec = getCachedSatrec(line1, line2);
    const date = new Date(timeMs);
    const positionAndVelocity = satellite.propagate(satrec, date);

    if (!positionAndVelocity || !positionAndVelocity.position || typeof positionAndVelocity.position === 'boolean') {
      return null;
    }

    const pos = positionAndVelocity.position as satellite.EciVec3<number>;
    const vel = (positionAndVelocity.velocity as satellite.EciVec3<number>) || { x: 0, y: 0, z: 0 };

    const distanceKm = Math.sqrt(pos.x * pos.x + pos.y * pos.y + pos.z * pos.z);
    const altitudeKm = Math.max(0, distanceKm - EARTH_RADIUS_KM);

    return {
      x: pos.x,
      y: pos.y,
      z: pos.z,
      vx: vel.x || 0,
      vy: vel.y || 0,
      vz: vel.z || 0,
      altitudeKm,
    };
  } catch {
    return null;
  }
}

/**
 * Generates an orbital trajectory ring for one full orbital period.
 */
export function generateOrbitPath(
  line1: string,
  line2: string,
  referenceTimeMs: number,
  samples = 72
): [number, number, number][] {
  const points: [number, number, number][] = [];
  try {
    const satrec = getCachedSatrec(line1, line2);
    const revsPerDay = satrec.no ? (satrec.no * 1440) / (2 * Math.PI) : 15.0;
    const periodMinutes = 1440 / (revsPerDay || 15.0);
    const periodMs = periodMinutes * 60 * 1000;
    const stepMs = periodMs / samples;

    for (let i = 0; i <= samples; i++) {
      const t = referenceTimeMs + (i - samples / 2) * stepMs;
      const date = new Date(t);
      const pv = satellite.propagate(satrec, date);
      if (pv && pv.position && typeof pv.position !== 'boolean') {
        const pos = pv.position as satellite.EciVec3<number>;
        points.push(eciKmToSceneCoords(pos.x, pos.y, pos.z));
      }
    }
  } catch {
    // fallback empty
  }
  return points;
}

/**
 * Propagate a window trajectory for SGP4 trajectory streaming.
 */
export function generateTrajectorySamples(
  line1: string,
  line2: string,
  startMs: number,
  endMs: number,
  stepSeconds = 60
): TrajectoryPoint[] {
  const points: TrajectoryPoint[] = [];
  try {
    const satrec = getCachedSatrec(line1, line2);
    const stepMs = stepSeconds * 1000;

    for (let t = startMs; t <= endMs; t += stepMs) {
      const date = new Date(t);
      const pv = satellite.propagate(satrec, date);
      if (pv && pv.position && typeof pv.position !== 'boolean') {
        const pos = pv.position as satellite.EciVec3<number>;
        const vel = (pv.velocity as satellite.EciVec3<number>) || { x: 0, y: 0, z: 0 };
        points.push({
          timeMs: t,
          x: pos.x,
          y: pos.y,
          z: pos.z,
          vx: vel.x,
          vy: vel.y,
          vz: vel.z,
        });
      }
    }
  } catch {
    // fallback
  }
  return points;
}

/**
 * Linear interpolation between trajectory points for smooth client-side animation.
 */
export function interpolateTrajectoryPoint(
  points: TrajectoryPoint[],
  targetTimeMs: number
): { x: number; y: number; z: number } | null {
  if (!points || points.length === 0) return null;
  if (targetTimeMs <= points[0].timeMs) {
    return { x: points[0].x, y: points[0].y, z: points[0].z };
  }
  const last = points[points.length - 1];
  if (targetTimeMs >= last.timeMs) {
    return { x: last.x, y: last.y, z: last.z };
  }

  let low = 0;
  let high = points.length - 1;
  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    if (points[mid].timeMs <= targetTimeMs && points[mid + 1]?.timeMs >= targetTimeMs) {
      const p1 = points[mid];
      const p2 = points[mid + 1];
      const factor = (targetTimeMs - p1.timeMs) / (p2.timeMs - p1.timeMs);
      return {
        x: p1.x + (p2.x - p1.x) * factor,
        y: p1.y + (p2.y - p1.y) * factor,
        z: p1.z + (p2.z - p1.z) * factor,
      };
    } else if (points[mid].timeMs < targetTimeMs) {
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }
  return { x: points[0].x, y: points[0].y, z: points[0].z };
}
