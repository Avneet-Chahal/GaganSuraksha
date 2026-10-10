import React, { useMemo } from 'react';
import * as THREE from 'three';
import { INDIAN_SATELLITES, ALL_SATELLITES_CATALOG } from '../../api/mockData';
import { generateOrbitPath } from '../../api/sgp4Service';
import { useSimulationStore } from '../../store/simulationStore';

export const OrbitLines: React.FC = () => {
  const showOrbits = useSimulationStore((s) => s.showOrbits);
  const selectedObjectId = useSimulationStore((s) => s.selectedObjectId);
  const highlightedConjunctionId = useSimulationStore((s) => s.highlightedConjunctionId);
  const orbitRegimeFilter = useSimulationStore((s) => s.orbitRegimeFilter);
  const simTimeMs = useSimulationStore((s) => s.simTimeMs);

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

  return (
    <group>
      {orbitsToRender.map((obj) => {
        const isSelected = selectedObjectId === obj.id;
        const isConjunctionHighlight = highlightedConjunctionId !== null;

        return (
          <SingleOrbitLine
            key={obj.id}
            object={obj}
            referenceTimeMs={simTimeMs}
            isSelected={isSelected}
            isConjunctionHighlight={isConjunctionHighlight}
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
}

const SingleOrbitLine: React.FC<SingleOrbitLineProps> = ({
  object,
  referenceTimeMs,
  isSelected,
}) => {
  const lineObject = useMemo(() => {
    const raw = generateOrbitPath(object.tleLine1, object.tleLine2, referenceTimeMs, 84);
    const points = raw.map(([x, y, z]) => new THREE.Vector3(x, y, z));
    const geom = new THREE.BufferGeometry().setFromPoints(points);

    const color = isSelected
      ? object.type === 'DEBRIS'
        ? 0xf59e0b
        : 0x00e5ff
      : object.type === 'DEBRIS'
      ? 0x64748b
      : 0x0284c7;

    const opacity = isSelected ? 0.75 : 0.22;
    const mat = new THREE.LineBasicMaterial({
      color,
      transparent: true,
      opacity,
      linewidth: isSelected ? 1.5 : 1.0,
      depthWrite: false,
    });

    return new THREE.Line(geom, mat);
  }, [object, referenceTimeMs, isSelected]);

  return <primitive object={lineObject} />;
};
