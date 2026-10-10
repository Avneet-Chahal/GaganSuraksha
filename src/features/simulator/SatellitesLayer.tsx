import React, { useRef, useMemo } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';
import { Html } from '@react-three/drei';
import { INDIAN_SATELLITES } from '../../api/mockData';
import { propagateTleAtTime, eciKmToSceneCoords } from '../../api/sgp4Service';
import { useSimulationStore } from '../../store/simulationStore';

export const SatellitesLayer: React.FC = () => {
  const showSatellites = useSimulationStore((s) => s.showSatellites);
  const orbitRegimeFilter = useSimulationStore((s) => s.orbitRegimeFilter);
  const selectedObjectId = useSimulationStore((s) => s.selectedObjectId);
  const hoveredObjectId = useSimulationStore((s) => s.hoveredObjectId);
  const selectObject = useSimulationStore((s) => s.selectObject);
  const setHoveredObject = useSimulationStore((s) => s.setHoveredObject);

  // Group containing satellite markers
  const groupRef = useRef<THREE.Group>(null);
  // Store satellite marker mesh refs
  const satMeshRefs = useRef<{ [id: string]: THREE.Mesh | null }>({});

  // Filter satellites according to regime
  const filteredSatellites = useMemo(() => {
    if (!showSatellites) return [];
    if (orbitRegimeFilter === 'ALL') return INDIAN_SATELLITES;
    return INDIAN_SATELLITES.filter((s) => s.regime === orbitRegimeFilter);
  }, [showSatellites, orbitRegimeFilter]);

  // Update positions every frame via SGP4 propagation
  useFrame(() => {
    const simTimeMs = useSimulationStore.getState().simTimeMs;
    for (const sat of filteredSatellites) {
      const mesh = satMeshRefs.current[sat.id];
      if (mesh) {
        const pv = propagateTleAtTime(sat.tleLine1, sat.tleLine2, simTimeMs);
        if (pv) {
          const [sx, sy, sz] = eciKmToSceneCoords(pv.x, pv.y, pv.z);
          mesh.position.set(sx, sy, sz);
          mesh.visible = true;
        } else {
          mesh.visible = false;
        }
      }
    }
  });

  if (!showSatellites) return null;

  return (
    <group ref={groupRef}>
      {filteredSatellites.map((sat) => {
        const isSelected = selectedObjectId === sat.id;
        const isHovered = hoveredObjectId === sat.id;

        return (
          <mesh
            key={sat.id}
            ref={(el) => {
              satMeshRefs.current[sat.id] = el;
            }}
            onClick={(e) => {
              e.stopPropagation();
              selectObject(sat.id);
            }}
            onPointerOver={(e) => {
              e.stopPropagation();
              setHoveredObject(sat.id);
              document.body.style.cursor = 'pointer';
            }}
            onPointerOut={() => {
              setHoveredObject(null);
              document.body.style.cursor = 'default';
            }}
          >
            {/* Satellite marker sphere */}
            <sphereGeometry args={[0.045, 12, 12]} />
            <meshBasicMaterial
              color={isSelected ? '#00e5ff' : isHovered ? '#7dd3fc' : '#38bdf8'}
            />

            {/* Selected object: bright ring plus clean label */}
            {isSelected && (
              <group>
                <mesh rotation={[Math.PI / 2, 0, 0]}>
                  <ringGeometry args={[0.08, 0.095, 32]} />
                  <meshBasicMaterial color="#38bdf8" side={THREE.DoubleSide} />
                </mesh>
                <Html
                  position={[0, 0.12, 0]}
                  center
                  distanceFactor={15}
                  className="pointer-events-none select-none"
                >
                  <div className="bg-[#0D131D]/90 backdrop-blur-sm border border-cyan-500/50 rounded px-2 py-1 text-[11px] font-mono text-cyan-300 shadow-md whitespace-nowrap">
                    <span className="font-semibold">{sat.name}</span>
                    <span className="text-slate-400 ml-1.5">#{sat.noradId}</span>
                  </div>
                </Html>
              </group>
            )}

            {/* Hover tooltip: small and clean without clutter */}
            {!isSelected && isHovered && (
              <Html
                position={[0, 0.09, 0]}
                center
                distanceFactor={15}
                className="pointer-events-none select-none"
              >
                <div className="bg-[#0D131D]/95 border border-slate-700 rounded px-2 py-0.5 text-[10px] font-mono text-slate-200 whitespace-nowrap shadow-sm">
                  {sat.name} <span className="text-slate-400">({sat.regime})</span>
                </div>
              </Html>
            )}
          </mesh>
        );
      })}
    </group>
  );
};
