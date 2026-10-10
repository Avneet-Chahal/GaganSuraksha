import React, { useRef, useMemo } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';
import { SCENE_EARTH_RADIUS, getGmstRadians } from '../../api/sgp4Service';
import { useSimulationStore } from '../../store/simulationStore';

// Procedural Earth texture creation for guaranteed offline/sandbox reliability
function createProceduralEarthTexture(): THREE.CanvasTexture {
  const canvas = document.createElement('canvas');
  canvas.width = 2048;
  canvas.height = 1024;
  const ctx = canvas.getContext('2d')!;

  // Deep aerospace ocean background
  const oceanGrad = ctx.createLinearGradient(0, 0, 0, canvas.height);
  oceanGrad.addColorStop(0, '#040b17');
  oceanGrad.addColorStop(0.5, '#071528');
  oceanGrad.addColorStop(1, '#040b17');
  ctx.fillStyle = oceanGrad;
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // Subtle coordinate grid (lat/lon lines at 30 deg intervals)
  ctx.strokeStyle = 'rgba(56, 189, 248, 0.08)';
  ctx.lineWidth = 1;

  for (let lat = 1; lat < 6; lat++) {
    const y = (canvas.height / 6) * lat;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(canvas.width, y);
    ctx.stroke();
  }
  for (let lon = 0; lon < 12; lon++) {
    const x = (canvas.width / 12) * lon;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, canvas.height);
    ctx.stroke();
  }

  // Draw simplified continents (Africa, Eurasia, Americas, India subcontinent, Australia)
  ctx.fillStyle = '#112233';
  ctx.strokeStyle = '#1b3a55';
  ctx.lineWidth = 1.5;

  const drawLand = (coords: [number, number][]) => {
    ctx.beginPath();
    coords.forEach(([nx, ny], idx) => {
      const px = nx * canvas.width;
      const py = ny * canvas.height;
      if (idx === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    });
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
  };

  // Africa & Middle East
  drawLand([
    [0.48, 0.38], [0.55, 0.38], [0.58, 0.45], [0.56, 0.55],
    [0.55, 0.70], [0.50, 0.75], [0.46, 0.60], [0.44, 0.48], [0.48, 0.38]
  ]);

  // Europe & Northern Eurasia
  drawLand([
    [0.45, 0.20], [0.58, 0.20], [0.75, 0.22], [0.85, 0.25],
    [0.82, 0.38], [0.65, 0.36], [0.52, 0.32], [0.45, 0.20]
  ]);

  // South Asia / India (prominently mapped)
  drawLand([
    [0.67, 0.36], [0.73, 0.36], [0.73, 0.44], [0.70, 0.52],
    [0.67, 0.46], [0.66, 0.40], [0.67, 0.36]
  ]);

  // East Asia & SE Asia
  drawLand([
    [0.74, 0.35], [0.84, 0.35], [0.82, 0.52], [0.76, 0.55],
    [0.72, 0.45], [0.74, 0.35]
  ]);

  // North America
  drawLand([
    [0.12, 0.20], [0.28, 0.22], [0.26, 0.38], [0.20, 0.45],
    [0.15, 0.40], [0.10, 0.28], [0.12, 0.20]
  ]);

  // South America
  drawLand([
    [0.22, 0.48], [0.32, 0.52], [0.30, 0.75], [0.24, 0.82],
    [0.20, 0.65], [0.22, 0.48]
  ]);

  // Australia
  drawLand([
    [0.78, 0.65], [0.88, 0.65], [0.87, 0.78], [0.79, 0.77], [0.78, 0.65]
  ]);

  // Highlight ISRO ground station (Sriharikota)
  ctx.fillStyle = '#38bdf8';
  ctx.beginPath();
  ctx.arc(0.722 * canvas.width, 0.424 * canvas.height, 3, 0, Math.PI * 2);
  ctx.fill();

  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.ClampToEdgeWrapping;
  return texture;
}

// Custom thin atmosphere rim shader
const AtmosphereShader = {
  vertexShader: `
    varying vec3 vNormal;
    varying vec3 vViewPosition;
    void main() {
      vNormal = normalize(normalMatrix * normal);
      vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
      vViewPosition = -mvPosition.xyz;
      gl_Position = projectionMatrix * mvPosition;
    }
  `,
  fragmentShader: `
    varying vec3 vNormal;
    varying vec3 vViewPosition;
    void main() {
      vec3 normal = normalize(vNormal);
      vec3 viewDir = normalize(vViewPosition);
      float rim = 1.0 - max(dot(viewDir, normal), 0.0);
      rim = pow(rim, 3.2);

      vec3 rimColor = vec3(0.08, 0.48, 0.68);
      gl_FragColor = vec4(rimColor, rim * 0.45);
    }
  `,
};

export const Earth: React.FC = () => {
  const earthMeshRef = useRef<THREE.Mesh>(null);
  const earthGroupRef = useRef<THREE.Group>(null);
  const atmosphereRef = useRef<THREE.Mesh>(null);

  const earthTexture = useMemo(() => createProceduralEarthTexture(), []);

  const atmosphereMaterial = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: AtmosphereShader.vertexShader,
        fragmentShader: AtmosphereShader.fragmentShader,
        blending: THREE.AdditiveBlending,
        side: THREE.BackSide,
        transparent: true,
        depthWrite: false,
      }),
    []
  );

  const equatorLoop = useMemo(() => {
    const points: THREE.Vector3[] = [];
    const segments = 64;
    for (let i = 0; i <= segments; i++) {
      const theta = (i / segments) * Math.PI * 2;
      points.push(new THREE.Vector3(Math.cos(theta) * 2.01, 0, Math.sin(theta) * 2.01));
    }
    const geom = new THREE.BufferGeometry().setFromPoints(points);
    const mat = new THREE.LineBasicMaterial({ color: 0x38bdf8, transparent: true, opacity: 0.15 });
    return new THREE.LineLoop(geom, mat);
  }, []);

  // Earth rotation driven strictly by simulation time (GMST)
  useFrame(() => {
    const simTimeMs = useSimulationStore.getState().simTimeMs;
    const gmst = getGmstRadians(simTimeMs);
    if (earthGroupRef.current) {
      earthGroupRef.current.rotation.y = gmst;
    }
  });

  return (
    <group ref={earthGroupRef}>
      {/* Primary Earth sphere */}
      <mesh ref={earthMeshRef}>
        <sphereGeometry args={[SCENE_EARTH_RADIUS, 64, 48]} />
        <meshStandardMaterial
          map={earthTexture}
          roughness={0.85}
          metalness={0.1}
          color="#dbeafe"
        />
      </mesh>

      {/* Atmospheric Rim Shell */}
      <mesh ref={atmosphereRef}>
        <sphereGeometry args={[SCENE_EARTH_RADIUS * 1.025, 48, 36]} />
        <primitive object={atmosphereMaterial} attach="material" />
      </mesh>

      {/* Subtle Equator Guide Ring */}
      <primitive object={equatorLoop} />
    </group>
  );
};
