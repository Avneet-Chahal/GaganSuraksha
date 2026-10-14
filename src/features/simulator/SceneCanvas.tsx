import React, { Suspense } from 'react';
import { Canvas } from '@react-three/fiber';
import { Earth } from './Earth';
import { SatellitesLayer } from './SatellitesLayer';
import { DebrisLayer } from './DebrisLayer';
import { OrbitLines } from './OrbitLines';
import { ConjunctionVisualizer } from './ConjunctionVisualizer';
import { CameraController } from './CameraController';
import { useSimulationStore } from '../../store/simulationStore';

function SimulationTimeTicker() {
  const advanceSimTime = useSimulationStore((s) => s.advanceSimTime);

  // Smooth client-side animation time advancement
  React.useEffect(() => {
    let lastTime = performance.now();
    let animId: number;

    const tick = (now: number) => {
      const deltaSec = (now - lastTime) / 1000;
      lastTime = now;
      advanceSimTime(deltaSec);
      animId = requestAnimationFrame(tick);
    };

    animId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animId);
  }, [advanceSimTime]);

  return null;
}

export const SceneCanvas: React.FC = () => {
  const selectObject = useSimulationStore((s) => s.selectObject);

  return (
    <div className="relative w-full h-full bg-[#070B12] overflow-hidden select-none">
      {/* Simulation time ticker running via requestAnimationFrame */}
      <SimulationTimeTicker />

      <Canvas
        camera={{ position: [0, 3.2, 5.8], fov: 45, near: 0.1, far: 1000 }}
        dpr={[1, 2]}
        gl={{
          antialias: true,
          powerPreference: 'high-performance',
          alpha: false,
        }}
        onPointerMissed={() => selectObject(null)}
      >
        <color attach="background" args={['#070B12']} />

        {/* Directional Sun light & subtle ambient fill */}
        <ambientLight intensity={0.25} />
        <directionalLight position={[12, 6, 10]} intensity={1.4} />

        <Suspense fallback={null}>
          <Earth />
          <OrbitLines />
          <DebrisLayer />
          <SatellitesLayer />
          <ConjunctionVisualizer />
          <CameraController />
        </Suspense>
      </Canvas>
    </div>
  );
};
