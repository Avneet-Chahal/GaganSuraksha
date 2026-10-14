import React, { useRef, useMemo, useEffect } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';
import { Html } from '@react-three/drei';
import { ALL_SATELLITES_CATALOG } from '../../api/mockData';
import { propagateTleAtTime, eciKmToSceneCoords } from '../../api/sgp4Service';
import { useSimulationStore } from '../../store/simulationStore';

export const DebrisLayer: React.FC = () => {
  const showDebris = useSimulationStore((s) => s.showDebris);
  const orbitRegimeFilter = useSimulationStore((s) => s.orbitRegimeFilter);
  const selectedObjectId = useSimulationStore((s) => s.selectedObjectId);
  const hoveredObjectId = useSimulationStore((s) => s.hoveredObjectId);
  const selectObject = useSimulationStore((s) => s.selectObject);
  const setHoveredObject = useSimulationStore((s) => s.setHoveredObject);

  const pointsRef = useRef<THREE.Points>(null);
  const posAttrRef = useRef<THREE.BufferAttribute>(null);

  // Filter debris objects
  const debrisList = useMemo(() => {
    return ALL_SATELLITES_CATALOG.filter((s) => {
      if (s.type !== 'DEBRIS') return false;
      if (orbitRegimeFilter !== 'ALL' && s.regime !== orbitRegimeFilter) return false;
      return true;
    });
  }, [orbitRegimeFilter]);

  const count = debrisList.length;

  // Float32Array position buffer for instanced points
  const [positions, colors] = useMemo(() => {
    const pos = new Float32Array(count * 3);
    const col = new Float32Array(count * 3);

    for (let i = 0; i < count; i++) {
      // Initialize with default color: dim grey-blue (e.g. #64748B)
      col[i * 3] = 0.45;
      col[i * 3 + 1] = 0.52;
      col[i * 3 + 2] = 0.62;
    }
    return [pos, col];
  }, [count]);

  // Selected debris object reference
  const selectedDebris = useMemo(() => {
    if (!selectedObjectId) return null;
    return debrisList.find((d) => d.id === selectedObjectId) || null;
  }, [selectedObjectId, debrisList]);

  // Update positions every frame via SGP4 propagation without causing React re-renders
  useFrame(() => {
    if (!showDebris || !posAttrRef.current) return;

    const simTimeMs = useSimulationStore.getState().simTimeMs;
    const array = posAttrRef.current.array as Float32Array;

    for (let i = 0; i < count; i++) {
      const item = debrisList[i];
      const pv = propagateTleAtTime(item.tleLine1, item.tleLine2, simTimeMs);
      if (pv) {
        const [x, y, z] = eciKmToSceneCoords(pv.x, pv.y, pv.z);
        array[i * 3] = x;
        array[i * 3 + 1] = y;
        array[i * 3 + 2] = z;
      }
    }
    posAttrRef.current.needsUpdate = true;
  });

  // Tracked high-priority debris can also be rendered with interactive targets
  const trackedPriorityDebris = useMemo(() => {
    return debrisList.filter((d) => ['38244', '34120', '30255', '41920', '39430'].includes(d.id));
  }, [debrisList]);

  // Clean up geometries on unmount
  useEffect(() => {
    const points = pointsRef.current;
    return () => {
      points?.geometry.dispose();
    };
  }, []);

  if (!showDebris || count === 0) return null;

  return (
    <group>
      {/* High-performance instanced points for all debris */}
      <points ref={pointsRef}>
        <bufferGeometry>
          <bufferAttribute
            ref={posAttrRef}
            attach="attributes-position"
            args={[positions, 3]}
          />
          <bufferAttribute
            attach="attributes-color"
            args={[colors, 3]}
          />
        </bufferGeometry>
        <pointsMaterial
          size={0.035}
          sizeAttenuation={true}
          vertexColors={true}
          transparent={true}
          opacity={0.7}
        />
      </points>

      {/* Interactive invisible hit areas for priority tracked debris */}
      {trackedPriorityDebris.map((deb) => {
        const isSelected = selectedObjectId === deb.id;
        const isHovered = hoveredObjectId === deb.id;

        return (
          <InteractiveDebrisMarker
            key={deb.id}
            debris={deb}
            isSelected={isSelected}
            isHovered={isHovered}
            onSelect={() => selectObject(deb.id)}
            onHover={(h) => setHoveredObject(h ? deb.id : null)}
          />
        );
      })}

      {/* Selected debris highlight reticle and label following target dynamically */}
      {selectedDebris && <SelectedDebrisMarker debris={selectedDebris} />}
    </group>
  );
};

interface SelectedDebrisMarkerProps {
  debris: (typeof ALL_SATELLITES_CATALOG)[0];
}

const SelectedDebrisMarker: React.FC<SelectedDebrisMarkerProps> = ({ debris }) => {
  const groupRef = useRef<THREE.Group>(null);

  useFrame(() => {
    const simTimeMs = useSimulationStore.getState().simTimeMs;
    const pv = propagateTleAtTime(debris.tleLine1, debris.tleLine2, simTimeMs);
    if (pv && groupRef.current) {
      const [x, y, z] = eciKmToSceneCoords(pv.x, pv.y, pv.z);
      groupRef.current.position.set(x, y, z);
    }
  });

  return (
    <group ref={groupRef}>
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.07, 0.085, 24]} />
        <meshBasicMaterial color="#f59e0b" side={THREE.DoubleSide} />
      </mesh>
      <Html position={[0, 0.1, 0]} center distanceFactor={15} className="pointer-events-none select-none">
        <div className="bg-[#0D131D]/90 border border-amber-500/50 rounded px-2 py-0.5 text-[10px] font-mono text-amber-300 whitespace-nowrap shadow-md">
          {debris.name} <span className="text-slate-400">#{debris.noradId}</span>
        </div>
      </Html>
    </group>
  );
};

interface InteractiveDebrisMarkerProps {
  debris: (typeof ALL_SATELLITES_CATALOG)[0];
  isSelected: boolean;
  isHovered: boolean;
  onSelect: () => void;
  onHover: (hovered: boolean) => void;
}

const InteractiveDebrisMarker: React.FC<InteractiveDebrisMarkerProps> = ({
  debris,
  isSelected,
  isHovered,
  onSelect,
  onHover,
}) => {
  const meshRef = useRef<THREE.Mesh>(null);

  useFrame(() => {
    const simTimeMs = useSimulationStore.getState().simTimeMs;
    const pv = propagateTleAtTime(debris.tleLine1, debris.tleLine2, simTimeMs);
    if (pv && meshRef.current) {
      const [x, y, z] = eciKmToSceneCoords(pv.x, pv.y, pv.z);
      meshRef.current.position.set(x, y, z);
    }
  });

  return (
    <mesh
      ref={meshRef}
      onClick={(e) => {
        e.stopPropagation();
        onSelect();
      }}
      onPointerOver={(e) => {
        e.stopPropagation();
        onHover(true);
        document.body.style.cursor = 'pointer';
      }}
      onPointerOut={() => {
        onHover(false);
        document.body.style.cursor = 'default';
      }}
    >
      <sphereGeometry args={[0.04, 8, 8]} />
      <meshBasicMaterial
        color={isSelected ? '#f59e0b' : isHovered ? '#fbbf24' : '#94a3b8'}
      />
      {!isSelected && isHovered && (
        <Html position={[0, 0.08, 0]} center distanceFactor={15} className="pointer-events-none select-none">
          <div className="bg-[#0D131D]/95 border border-slate-700 rounded px-2 py-0.5 text-[10px] font-mono text-slate-200 whitespace-nowrap shadow-sm">
            {debris.name} <span className="text-amber-400">#DEB</span>
          </div>
        </Html>
      )}
    </mesh>
  );
};
