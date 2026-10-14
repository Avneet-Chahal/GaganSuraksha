import React, { useMemo, useEffect } from 'react';
import * as THREE from 'three';
import { Html } from '@react-three/drei';
import { CONJUNCTION_EVENTS } from '../../api/mockData';
import {
  generateOrbitPath,
  propagateTleAtTime,
  eciKmToSceneCoords,
} from '../../api/sgp4Service';
import { useSimulationStore } from '../../store/simulationStore';
import { formatUtcShort } from '../../hooks/useUtcClock';

export const ConjunctionVisualizer: React.FC = () => {
  const highlightedConjunctionId = useSimulationStore((s) => s.highlightedConjunctionId);

  const conjunction = useMemo(() => {
    if (!highlightedConjunctionId) return null;
    return CONJUNCTION_EVENTS.find((c) => c.id === highlightedConjunctionId);
  }, [highlightedConjunctionId]);

  const { primarySat, secondarySat, tcaMs, missDistanceKm, relativeVelocityKmS, riskLevel } =
    conjunction || {
      primarySat: null,
      secondarySat: null,
      tcaMs: 0,
      missDistanceKm: 0,
      relativeVelocityKmS: 0,
      riskLevel: 'NOMINAL' as const,
    };

  // Propagate positions of both objects at TCA
  const primaryTcaCoords = useMemo((): [number, number, number] => {
    if (!primarySat) return [0, 0, 0];
    const pv = propagateTleAtTime(primarySat.tleLine1, primarySat.tleLine2, tcaMs);
    return pv ? eciKmToSceneCoords(pv.x, pv.y, pv.z) : [0, 0, 0];
  }, [primarySat, tcaMs]);

  const secondaryTcaCoords = useMemo((): [number, number, number] => {
    if (!secondarySat) return [0, 0, 0];
    const pv = propagateTleAtTime(secondarySat.tleLine1, secondarySat.tleLine2, tcaMs);
    return pv ? eciKmToSceneCoords(pv.x, pv.y, pv.z) : [0, 0, 0];
  }, [secondarySat, tcaMs]);

  // Compute full orbit rings for both objects
  const primaryLineObj = useMemo(() => {
    if (!primarySat) return null;
    const points = generateOrbitPath(primarySat.tleLine1, primarySat.tleLine2, tcaMs, 96).map(
      ([x, y, z]) => new THREE.Vector3(x, y, z)
    );
    const geom = new THREE.BufferGeometry().setFromPoints(points);
    const mat = new THREE.LineBasicMaterial({
      color: 0x38bdf8,
      linewidth: 1.5,
      transparent: true,
      opacity: 0.8,
    });
    return new THREE.Line(geom, mat);
  }, [primarySat, tcaMs]);

  const riskColor = riskLevel === 'CRITICAL' ? 0xf43f5e : riskLevel === 'WARNING' ? 0xf59e0b : 0x10b981;
  const riskColorHex = riskLevel === 'CRITICAL' ? '#f43f5e' : riskLevel === 'WARNING' ? '#f59e0b' : '#10b981';

  const secondaryLineObj = useMemo(() => {
    if (!secondarySat) return null;
    const points = generateOrbitPath(secondarySat.tleLine1, secondarySat.tleLine2, tcaMs, 96).map(
      ([x, y, z]) => new THREE.Vector3(x, y, z)
    );
    const geom = new THREE.BufferGeometry().setFromPoints(points);
    const mat = new THREE.LineBasicMaterial({
      color: riskColor,
      linewidth: 1.5,
      transparent: true,
      opacity: 0.8,
    });
    return new THREE.Line(geom, mat);
  }, [secondarySat, tcaMs, riskColor]);

  // Separation line geometry between the two objects at TCA
  const separationLineObj = useMemo(() => {
    const p1 = new THREE.Vector3(...primaryTcaCoords);
    const p2 = new THREE.Vector3(...secondaryTcaCoords);
    const geom = new THREE.BufferGeometry().setFromPoints([p1, p2]);
    const mat = new THREE.LineBasicMaterial({
      color: 0xffffff,
      linewidth: 2,
      transparent: true,
      opacity: 0.9,
    });
    return new THREE.Line(geom, mat);
  }, [primaryTcaCoords, secondaryTcaCoords]);

  // Clean up geometries and materials on unmount/recalculation
  useEffect(() => {
    return () => {
      primaryLineObj?.geometry.dispose();
      if (primaryLineObj?.material) {
        if (Array.isArray(primaryLineObj.material)) {
          primaryLineObj.material.forEach((m) => m.dispose());
        } else {
          primaryLineObj.material.dispose();
        }
      }
    };
  }, [primaryLineObj]);

  useEffect(() => {
    return () => {
      secondaryLineObj?.geometry.dispose();
      if (secondaryLineObj?.material) {
        if (Array.isArray(secondaryLineObj.material)) {
          secondaryLineObj.material.forEach((m) => m.dispose());
        } else {
          secondaryLineObj.material.dispose();
        }
      }
    };
  }, [secondaryLineObj]);

  useEffect(() => {
    return () => {
      separationLineObj?.geometry.dispose();
      if (separationLineObj?.material) {
        if (Array.isArray(separationLineObj.material)) {
          separationLineObj.material.forEach((m) => m.dispose());
        } else {
          separationLineObj.material.dispose();
        }
      }
    };
  }, [separationLineObj]);

  if (!conjunction || !primaryLineObj || !secondaryLineObj || !separationLineObj) {
    return null;
  }

  // Midpoint for floating badge
  const midPoint: [number, number, number] = [
    (primaryTcaCoords[0] + secondaryTcaCoords[0]) / 2,
    (primaryTcaCoords[1] + secondaryTcaCoords[1]) / 2,
    (primaryTcaCoords[2] + secondaryTcaCoords[2]) / 2,
  ];

  return (
    <group>
      {/* Primary Satellite Orbit (Cyan) */}
      <primitive object={primaryLineObj} />

      {/* Secondary Debris Orbit (Contrast Amber/Rose) */}
      <primitive object={secondaryLineObj} />

      {/* Connecting Miss Distance Line at TCA */}
      <primitive object={separationLineObj} />

      {/* Markers at TCA */}
      <mesh position={primaryTcaCoords}>
        <sphereGeometry args={[0.04, 12, 12]} />
        <meshBasicMaterial color="#38bdf8" />
      </mesh>

      <mesh position={secondaryTcaCoords}>
        <sphereGeometry args={[0.04, 12, 12]} />
        <meshBasicMaterial color={riskColorHex} />
      </mesh>

      {/* Floating TCA Information Tag */}
      <Html position={midPoint} center distanceFactor={14} className="pointer-events-none select-none">
        <div className="bg-[#070B12]/95 border border-white/20 rounded p-2 text-xs font-mono shadow-2xl backdrop-blur-md">
          <div className="flex items-center gap-1.5 text-slate-200 font-semibold mb-0.5">
            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: riskColorHex }} />
            <span>TCA: {formatUtcShort(tcaMs)}</span>
          </div>
          <div className="text-[11px] text-slate-300 flex items-center gap-2">
            <span>
              Miss: <strong className="text-white">{missDistanceKm.toFixed(3)} km</strong>
            </span>
            <span>•</span>
            <span>
              Rel V: <strong className="text-white">{relativeVelocityKmS.toFixed(2)} km/s</strong>
            </span>
          </div>
        </div>
      </Html>
    </group>
  );
};
