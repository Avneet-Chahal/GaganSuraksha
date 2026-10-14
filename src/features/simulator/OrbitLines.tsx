import React, { useMemo, useEffect } from 'react';
import * as THREE from 'three';
import { INDIAN_SATELLITES, ALL_SATELLITES_CATALOG } from '../../api/mockData';
import { generateOrbitPath, eciKmToSceneCoords } from '../../api/sgp4Service';
import { useSimulationStore } from '../../store/simulationStore';
import { useTrajectories } from '../../api/client';

export const OrbitLines: React.FC = () => {
  const showOrbits = useSimulationStore((s) => s.showOrbits);
  const selectedObjectId = useSimulationStore((s) => s.selectedObjectId);
  const highlightedConjunctionId = useSimulationStore((s) => s.highlightedConjunctionId);
  const orbitRegimeFilter = useSimulationStore((s) => s.orbitRegimeFilter);
  const useMlCorrectedOrbits = useSimulationStore((s) => s.useMlCorrectedOrbits);
  // Use fixed reference time (startWindowMs) instead of simTimeMs to avoid per-frame geometry rebuilds
  const startWindowMs = useSimulationStore((s) => s.startWindowMs);

  // Determine which objects should have orbit lines rendered
  const orbitsToRender = useMemo(() => {
    if (showOrbits === 'NONE' && !selectedObjectId) {
      return [];
    }

    const set = new Map<string, (typeof ALL_SATELLITES_CATALOG)[0]>();

    // Always include selected object if present
    if (selectedObjectId) {
      const selectedObj = ALL_SATELLITES_CATALOG.find((s) => s.id === selectedObjectId);
      if (selectedObj) set.set(selectedObj.id, selectedObj);
    }

    // Default mode: Watchlist Indian satellites
    if (showOrbits === 'WATCHLIST') {
      INDIAN_SATELLITES.forEach((sat) => {
        if (sat.isWatchlist) {
          if (orbitRegimeFilter === 'ALL' || sat.regime === orbitRegimeFilter) {
            set.set(sat.id, sat);
          }
        }
      });
    } else if (showOrbits === 'ALL') {
      // All Indian satellites plus priority tracked objects
      ALL_SATELLITES_CATALOG.slice(0, 35).forEach((sat) => {
        if (orbitRegimeFilter === 'ALL' || sat.regime === orbitRegimeFilter) {
          set.set(sat.id, sat);
        }
      });
    }

    return Array.from(set.values());
  }, [showOrbits, selectedObjectId, orbitRegimeFilter]);

  // Fetch ML-corrected trajectories from the API when toggle is active
  const idsToFetch = useMemo(() => {
    if (!useMlCorrectedOrbits) return [];
    return orbitsToRender.slice(0, 20).map((s) => s.id);
  }, [useMlCorrectedOrbits, orbitsToRender]);

  const startUtc = useMemo(() => new Date(startWindowMs).toISOString(), [startWindowMs]);
  const endUtc = useMemo(
    () => new Date(startWindowMs + 6 * 3600 * 1000).toISOString(),
    [startWindowMs]
  );

  const { data: trajectoryData } = useTrajectories(
    idsToFetch,
    startUtc,
    endUtc,
    120,
    useMlCorrectedOrbits
  );

  const apiPointsMap = useMemo(() => {
    const map = new Map<string, { x: number; y: number; z: number }[]>();
    if (useMlCorrectedOrbits && trajectoryData?.data) {
      for (const traj of trajectoryData.data) {
        if (traj.points && traj.points.length > 0) {
          map.set(traj.satelliteId, traj.points);
        }
      }
    }
    return map;
  }, [useMlCorrectedOrbits, trajectoryData]);

  return (
    <group>
      {orbitsToRender.map((obj) => {
        const isSelected = selectedObjectId === obj.id;
        const isConjunctionHighlight = highlightedConjunctionId !== null;

        return (
          <SingleOrbitLine
            key={obj.id}
            object={obj}
            referenceTimeMs={startWindowMs}
            isSelected={isSelected}
            isConjunctionHighlight={isConjunctionHighlight}
            pointsFromApi={apiPointsMap.get(obj.id)}
            isMlCorrected={useMlCorrectedOrbits}
          />
        );
      })}
    </group>
  );
};

interface SingleOrbitLineProps {
  object: (typeof ALL_SATELLITES_CATALOG)[0];
  referenceTimeMs: number;
  isSelected: boolean;
  isConjunctionHighlight: boolean;
  pointsFromApi?: { x: number; y: number; z: number }[];
  isMlCorrected?: boolean;
}

const SingleOrbitLine: React.FC<SingleOrbitLineProps> = ({
  object,
  referenceTimeMs,
  isSelected,
  pointsFromApi,
  isMlCorrected,
}) => {
  const lineObject = useMemo(() => {
    let points: THREE.Vector3[];
    if (pointsFromApi && pointsFromApi.length > 0) {
      points = pointsFromApi.map((pt) => {
        const [sx, sy, sz] = eciKmToSceneCoords(pt.x, pt.y, pt.z);
        return new THREE.Vector3(sx, sy, sz);
      });
    } else {
      const raw = generateOrbitPath(object.tleLine1, object.tleLine2, referenceTimeMs, 84);
      points = raw.map(([x, y, z]) => new THREE.Vector3(x, y, z));
    }
    const geom = new THREE.BufferGeometry().setFromPoints(points);

    const color = isSelected
      ? object.type === 'DEBRIS'
        ? 0xf59e0b
        : 0x00e5ff
      : isMlCorrected
      ? 0x06b6d4
      : object.type === 'DEBRIS'
      ? 0x64748b
      : 0x0284c7;

    const opacity = isSelected ? 0.8 : isMlCorrected ? 0.45 : 0.22;
    const mat = new THREE.LineBasicMaterial({
      color,
      transparent: true,
      opacity,
      linewidth: isSelected ? 1.5 : 1.0,
      depthWrite: false,
    });

    return new THREE.Line(geom, mat);
  }, [object, referenceTimeMs, isSelected, pointsFromApi, isMlCorrected]);

  // Dispose geometry and material on unmount or when lineObject changes
  useEffect(() => {
    return () => {
      lineObject.geometry.dispose();
      if (Array.isArray(lineObject.material)) {
        lineObject.material.forEach((m) => m.dispose());
      } else {
        lineObject.material.dispose();
      }
    };
  }, [lineObject]);

  return <primitive object={lineObject} />;
};
