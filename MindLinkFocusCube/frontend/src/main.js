import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import './styles.css';
import {
  brainShellPoint,
  cubeHeightFromAttention,
  lerp,
  particleParamsFromBands,
  prefrontalWeight,
} from './math.js';

const state = {
  attention: 0.5,
  targetAttention: 0.5,
  quality: 0,
  mode: 'waiting',
  device: {},
  normalized: { alpha: 0.35, beta: 0.2, gamma: 0.1, betaGamma: 0.15 },
  connected: false,
};

const ui = {
  attention: document.querySelector('#attention-value'),
  mode: document.querySelector('#mode-value'),
  quality: document.querySelector('#quality-value'),
  connection: document.querySelector('#connection-value'),
  deviceState: document.querySelector('#device-state-value'),
  battery: document.querySelector('#battery-value'),
  port: document.querySelector('#port-value'),
  samples: document.querySelector('#samples-value'),
};

function renderDeviceBadge() {
  const mode = state.mode;
  const device = state.device || {};
  const hasRealDevice = mode === 'device' || mode === 'device_warming';
  const label = mode === 'device'
    ? 'real device'
    : mode === 'device_warming'
      ? 'warming'
      : mode === 'demo'
        ? 'demo'
        : state.connected
          ? 'connected'
          : 'disconnected';

  ui.deviceState.textContent = label;
  ui.battery.textContent = device.battery == null ? '--' : `${device.battery}%`;
  ui.port.textContent = device.port || '--';
  ui.samples.textContent = String(device.sampleCount ?? 0);
  document.body.dataset.mode = hasRealDevice ? 'device' : mode;
}

function createRenderer(canvas) {
  const renderer = new THREE.WebGLRenderer({
    canvas,
    antialias: true,
    alpha: false,
    preserveDrawingBuffer: true,
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  return renderer;
}

function resizeRenderer(renderer, camera) {
  const canvas = renderer.domElement;
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  if (canvas.width !== Math.floor(width) || canvas.height !== Math.floor(height)) {
    renderer.setSize(width, height, false);
    camera.aspect = width / Math.max(height, 1);
    camera.updateProjectionMatrix();
  }
}

function setupCubeScene() {
  const canvas = document.querySelector('#cube-canvas');
  const renderer = createRenderer(canvas);
  renderer.setClearColor(0x101418);

  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(0x101418, 8, 18);

  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
  camera.position.set(4.2, 3.4, 6.2);
  camera.lookAt(0, 0.4, 0);

  const cube = new THREE.Mesh(
    new THREE.BoxGeometry(1.25, 1.25, 1.25),
    new THREE.MeshStandardMaterial({
      color: 0x7bc7ff,
      roughness: 0.42,
      metalness: 0.18,
      emissive: 0x12324a,
    }),
  );
  cube.position.y = cubeHeightFromAttention(state.attention);
  scene.add(cube);

  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(8, 8, 20, 20),
    new THREE.MeshStandardMaterial({
      color: 0x20262d,
      roughness: 0.8,
      metalness: 0.05,
      wireframe: true,
    }),
  );
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = -2.08;
  scene.add(floor);

  const liftRail = new THREE.Mesh(
    new THREE.CylinderGeometry(0.018, 0.018, 4.2, 16),
    new THREE.MeshBasicMaterial({ color: 0x52616f }),
  );
  liftRail.position.set(-1.65, 0.05, -0.2);
  scene.add(liftRail);

  scene.add(new THREE.HemisphereLight(0xdceeff, 0x20242a, 1.8));
  const key = new THREE.DirectionalLight(0xffffff, 2.2);
  key.position.set(3, 5, 4);
  scene.add(key);

  return {
    render(time) {
      resizeRenderer(renderer, camera);
      state.attention = lerp(state.attention, state.targetAttention, 0.08);
      cube.position.y = cubeHeightFromAttention(state.attention);
      cube.rotation.x = time * 0.0007;
      cube.rotation.y = time * 0.0011;
      renderer.render(scene, camera);
    },
  };
}

const BRAIN_PARTICLE_COUNT = 5000;

function createParticleCloud(color, count, mode) {
  const positions = new Float32Array(count * 3);
  const basePositions = new Float32Array(count * 3);
  const prefrontalWeights = new Float32Array(count);

  for (let i = 0; i < count; i += 1) {
    const hemisphere = i % 2 === 0 ? 'left' : 'right';
    const angleUnit = (i * 0.61803398875) % 1;
    const radiusUnit = mode === 'prefrontal'
      ? 0.46 + Math.random() * 0.54
      : Math.random();
    const point = brainShellPoint(angleUnit, radiusUnit, hemisphere);
    const frontal = prefrontalWeight(point);
    const frontalPull = mode === 'prefrontal' ? frontal * 0.52 : 0;
    const x = point.x * (1 - frontalPull * 0.2);
    const y = point.y + frontalPull * 0.38;
    const z = point.z + (Math.random() - 0.5) * 0.06;

    positions[i * 3] = x;
    positions[i * 3 + 1] = y;
    positions[i * 3 + 2] = z;
    basePositions[i * 3] = x;
    basePositions[i * 3 + 1] = y;
    basePositions[i * 3 + 2] = z;
    prefrontalWeights[i] = frontal;
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setDrawRange(0, count);

  const material = new THREE.PointsMaterial({
    color,
    size: 0.014,
    transparent: true,
    opacity: 0.55,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });

  const points = new THREE.Points(geometry, material);
  points.userData.basePositions = basePositions;
  points.userData.prefrontalWeights = prefrontalWeights;
  points.userData.mode = mode;
  return points;
}

function createBrainOutlineLine(points, color = 0x52616f, opacity = 0.48) {
  const geometry = new THREE.BufferGeometry().setFromPoints(points);
  const material = new THREE.LineBasicMaterial({ color, transparent: true, opacity });
  return new THREE.LineLoop(geometry, material);
}

function createTopDownBrainStructure() {
  const group = new THREE.Group();

  for (const hemisphere of ['left', 'right']) {
    const outline = [];
    for (let i = 0; i < 160; i += 1) {
      const point = brainShellPoint(i / 160, 1, hemisphere);
      outline.push(new THREE.Vector3(point.x, point.y, point.z - 0.06));
    }
    group.add(createBrainOutlineLine(outline, 0x6f7f8d, 0.5));

    for (let ring = 0; ring < 6; ring += 1) {
      const contour = [];
      const radius = 0.28 + ring * 0.11;
      for (let i = 0; i < 120; i += 1) {
        const point = brainShellPoint(i / 120 + ring * 0.017, radius, hemisphere);
        contour.push(new THREE.Vector3(point.x, point.y, point.z + 0.02));
      }
      group.add(createBrainOutlineLine(contour, 0x9aa8b7, 0.16));
    }
  }

  const fissurePoints = [];
  for (let i = 0; i <= 90; i += 1) {
    const y = -1.15 + (i / 90) * 2.55;
    const x = Math.sin(i * 0.22) * 0.035;
    fissurePoints.push(new THREE.Vector3(x, y, 0.03));
  }
  const fissure = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(fissurePoints),
    new THREE.LineBasicMaterial({ color: 0xc3ccd6, transparent: true, opacity: 0.45 }),
  );
  group.add(fissure);

  const prefrontalRing = createBrainOutlineLine(
    Array.from({ length: 96 }, (_, i) => {
      const angle = (i / 96) * Math.PI * 2;
      return new THREE.Vector3(Math.cos(angle) * 0.72, 1.18 + Math.sin(angle) * 0.24, 0.08);
    }),
    0xff007f,
    0.34,
  );
  group.add(prefrontalRing);

  return group;
}

function setupBrainScene() {
  const canvas = document.querySelector('#brain-canvas');
  const renderer = createRenderer(canvas);
  renderer.setClearColor(0x05070a);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
  camera.position.set(0, 0, 5.9);
  camera.lookAt(0, 0, 0);

  const root = new THREE.Group();
  scene.add(root);

  const fallback = createTopDownBrainStructure();
  root.add(fallback);

  const loader = new GLTFLoader();
  loader.load(
    '/models/cortex.glb',
    (gltf) => {
      root.remove(fallback);
      const model = gltf.scene;
      model.scale.setScalar(1.7);
      model.traverse((child) => {
        if (child.isMesh) {
          child.material = new THREE.MeshStandardMaterial({
            color: 0xaeb7c0,
            roughness: 0.7,
            transparent: true,
            opacity: 0.48,
          });
        }
      });
      root.add(model);
    },
    undefined,
    () => undefined,
  );

  const blue = createParticleCloud(0x00f3ff, BRAIN_PARTICLE_COUNT, 'distributed');
  const pink = createParticleCloud(0xff007f, BRAIN_PARTICLE_COUNT, 'prefrontal');
  root.add(blue, pink);

  scene.add(new THREE.HemisphereLight(0xeaf5ff, 0x20242a, 1.6));
  const key = new THREE.DirectionalLight(0xffffff, 1.8);
  key.position.set(2, 3, 4);
  scene.add(key);

  return {
    render(time) {
      resizeRenderer(renderer, camera);
      const params = particleParamsFromBands(state.normalized);
      animateBrainParticles(blue, params.blue, state.normalized.alpha, time);
      animateBrainParticles(pink, params.pink, state.normalized.betaGamma, time);
      blue.geometry.setDrawRange(0, params.blue.activeCount);
      blue.material.opacity = params.blue.opacity;
      blue.material.size = params.blue.size;
      pink.geometry.setDrawRange(0, params.pink.activeCount);
      pink.material.opacity = params.pink.opacity;
      pink.material.size = params.pink.size;
      root.rotation.z = Math.sin(time * 0.00022) * 0.035;
      renderer.render(scene, camera);
    },
  };
}

function animateBrainParticles(points, params, intensity, time) {
  const position = points.geometry.attributes.position;
  const base = points.userData.basePositions;
  const weights = points.userData.prefrontalWeights;
  const mode = points.userData.mode;
  const speed = mode === 'prefrontal' ? 0.006 + intensity * 0.014 : 0.003 + intensity * 0.006;
  const expansion = mode === 'prefrontal' ? 0.035 + intensity * 0.18 : 0.02 + intensity * 0.12;

  for (let i = 0; i < position.count; i += 1) {
    const ix = i * 3;
    const weight = mode === 'prefrontal' ? weights[i] : 0.55;
    const wave = Math.sin(time * speed + i * 0.09) * expansion * weight;
    const spark = mode === 'prefrontal' && Math.sin(time * 0.02 + i * 7.13) > 0.985
      ? intensity * 0.32 * weight
      : 0;
    const scale = 1 + wave + spark;
    position.array[ix] = base[ix] * scale;
    position.array[ix + 1] = base[ix + 1] * scale + spark * 0.24;
    position.array[ix + 2] = base[ix + 2] + Math.sin(time * speed + i) * 0.025 * intensity;
  }

  points.material.size = params.size;
  position.needsUpdate = true;
}

function connectWebSocket() {
  const socket = new WebSocket('ws://127.0.0.1:8765');

  socket.addEventListener('open', () => {
    state.connected = true;
    ui.connection.textContent = 'connected';
    renderDeviceBadge();
  });

  socket.addEventListener('message', (event) => {
    const payload = JSON.parse(event.data);
    state.targetAttention = Number(payload.attention ?? 0.5);
    state.quality = Number(payload.quality ?? 0);
    state.mode = payload.mode ?? 'unknown';
    state.device = payload.device ?? {};
    state.normalized = payload.normalized ?? state.normalized;
    ui.attention.textContent = state.targetAttention.toFixed(2);
    ui.mode.textContent = state.mode;
    ui.quality.textContent = state.quality.toFixed(2);
    renderDeviceBadge();
  });

  socket.addEventListener('close', () => {
    state.connected = false;
    state.mode = 'disconnected';
    state.device = {};
    ui.connection.textContent = 'disconnected';
    state.targetAttention = 0.5;
    renderDeviceBadge();
    setTimeout(connectWebSocket, 1200);
  });

  socket.addEventListener('error', () => {
    ui.connection.textContent = 'retrying';
  });
}

const cubeScene = setupCubeScene();
const brainScene = setupBrainScene();
connectWebSocket();

function animate(time) {
  cubeScene.render(time);
  brainScene.render(time);
  requestAnimationFrame(animate);
}

requestAnimationFrame(animate);
