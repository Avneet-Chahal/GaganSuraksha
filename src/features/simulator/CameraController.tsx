import React, { useRef, useEffect } from 'react';
import * as THREE from 'three';
import { useThree, useFrame } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib';
import { ALL_SATELLITES_CATALOG } from '../../api/mockData';
import { propagateTleAtTime, eciKmToSceneCoords } from '../../api/sgp4Service';
import { useSimulationStore } from '../../store/simulationStore';

export const CameraController: React.FC = () => {
  const controlsRef = useRef<OrbitControlsImpl>(null);
  const { camera } = useThree();

  const focusedObjectId = useSimulationStore((s) => s.focusedObjectId);

  // Initial camera setup
  useEffect(() => {
    camera.position.set(0, 3.2, 5.8);
    camera.lookAt(0, 0, 0);
  }, [camera]);

  // Smoothly follow focused object if set
  useFrame(() => {
    if (!controlsRef.current) return;

    const targetId = focusedObjectId || null;
    if (targetId) {
      const obj = ALL_SATELLITES_CATALOG.find((s) => s.id === targetId);
      if (obj) {
        const simTimeMs = useSimulationStore.getState().simTimeMs;
        const pv = propagateTleAtTime(obj.tleLine1, obj.tleLine2, simTimeMs);
        if (pv) {
          const [tx, ty, tz] = eciKmToSceneCoords(pv.x, pv.y, pv.z);
          controlsRef.current.target.lerp(new THREE.Vector3(tx, ty, tz), 0.08);
        }
      }
    }
  });

  return (
    <OrbitControls
      ref={controlsRef}
      enableDamping={true}
      dampingFactor={0.06}
      minDistance={2.25}
      maxDistance={28.0}
      rotateSpeed={0.65}
      zoomSpeed={0.8}
    />
  );
};

export function resetCameraView(camera: THREE.Camera, controls?: OrbitControlsImpl | null) {
  if (controls) {
    controls.target.set(0, 0, 0);
  }
  camera.position.set(0, 3.2, 5.8);
  camera.lookAt(0, 0, 0);
}
