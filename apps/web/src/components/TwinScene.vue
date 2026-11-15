<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue"
import * as THREE from "three"
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js"
import type { ScenePayload } from "../demo"

const props = defineProps<{ scene: ScenePayload | null; still?: boolean }>()
const host = ref<HTMLDivElement | null>(null)

let renderer: THREE.WebGLRenderer | null = null
let camera: THREE.PerspectiveCamera | null = null
let controls: OrbitControls | null = null
let frame = 0
let dragging = false
let resumeAt = 0
const root = new THREE.Group()
const dynamic = new THREE.Group()
const world = new THREE.Scene()

function up(point: number[]) {
  return new THREE.Vector3(point[0], point[2], point[1])
}

function material(color: number, roughness = 0.86) {
  return new THREE.MeshStandardMaterial({ color, roughness, metalness: 0.04 })
}

function addBox(min: number[], max: number[], color: number) {
  const size = new THREE.Vector3(max[0] - min[0], max[2] - min[2], max[1] - min[1])
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(size.x, size.y, size.z), material(color))
  mesh.position.set((min[0] + max[0]) / 2, (min[2] + max[2]) / 2, (min[1] + max[1]) / 2)
  mesh.castShadow = true
  mesh.receiveShadow = true
  root.add(mesh)
}

function buildRoom(scene: ScenePayload) {
  while (root.children.length) {
    const child = root.children[0]
    root.remove(child)
  }
  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(scene.width_m, scene.depth_m),
    material(0xc9c3b6, 0.92),
  )
  floor.rotation.x = -Math.PI / 2
  floor.position.set(scene.width_m / 2, 0, scene.depth_m / 2)
  floor.receiveShadow = true
  root.add(floor)
  const wall = 0.06
  addBox([0, 0, 0], [wall, scene.depth_m, scene.height_m], 0xe4dfd6)
  addBox([scene.width_m - wall, 0, 0], [scene.width_m, scene.depth_m, scene.height_m], 0xddd8cf)
  addBox([0, 0, 0], [scene.width_m, wall, scene.height_m], 0xe8e3da)
  addBox([0, scene.depth_m - wall, 0], [scene.width_m, scene.depth_m, scene.height_m], 0xd9d3c9)
  const colors: Record<string, number> = { desk: 0x8d6b45, cabinet: 0x3e4650, board: 0x2f463c }
  for (const item of scene.furniture) addBox(item.min, item.max, colors[item.kind] ?? 0x888888)
  const target = new THREE.Vector3(scene.width_m / 2, 1.2, scene.depth_m / 2)
  if (camera && controls) {
    controls.target.copy(target)
    camera.position.set(scene.width_m * 0.15, scene.height_m * 2.1, scene.depth_m * 1.35)
    controls.update()
  }
}

function line(points: THREE.Vector3[], color: number) {
  const geometry = new THREE.BufferGeometry().setFromPoints(points)
  return new THREE.Line(geometry, new THREE.LineBasicMaterial({ color }))
}

function polygon(points: number[][] | undefined, color: number, height: number) {
  if (!points || points.length < 2) return
  const ring = points.map((point) => new THREE.Vector3(point[0], height, point[1]))
  if (ring.length > 2) ring.push(ring[0].clone())
  dynamic.add(line(ring, color))
}

function refresh(scene: ScenePayload) {
  while (dynamic.children.length) dynamic.remove(dynamic.children[0])
  for (const item of scene.cameras) {
    const eye = up(item.eye)
    const marker = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.08, 0.1), material(0x243140, 0.45))
    marker.position.copy(eye)
    dynamic.add(marker)
    const forward = up(item.forward).normalize()
    const upright = up(item.up).normalize()
    const right = up(item.right).normalize()
    const reach = 1.5
    const halfY = Math.tan((item.fov_y_deg * Math.PI) / 360) * reach
    const halfX = halfY * (480 / 270)
    const center = eye.clone().add(forward.clone().multiplyScalar(reach))
    const corners = [-1, 1].flatMap((sy) =>
      [-1, 1].map((sx) =>
        center
          .clone()
          .add(right.clone().multiplyScalar(sx * halfX))
          .add(upright.clone().multiplyScalar(sy * halfY)),
      ),
    )
    for (const corner of corners) dynamic.add(line([eye, corner], 0x7d92a3))
    dynamic.add(line([corners[0], corners[1], corners[3], corners[2], corners[0]], 0x7d92a3))
    if (scene.fire) dynamic.add(line([eye, up(scene.fire.xyz)], 0xc4844a))
  }
  if (scene.fire) {
    const fire = new THREE.Mesh(new THREE.SphereGeometry(0.06, 18, 12), material(0xd4652f, 0.55))
    fire.position.copy(up(scene.fire.xyz))
    dynamic.add(fire)
    const ellipsoid = new THREE.Mesh(
      new THREE.SphereGeometry(1, 20, 14),
      new THREE.MeshStandardMaterial({ color: 0xd4652f, transparent: true, opacity: 0.28, roughness: 0.7 }),
    )
    const axes = scene.fire.axes
    const basis = new THREE.Matrix4().makeBasis(
      up([axes[0][0], axes[1][0], axes[2][0]]).normalize(),
      up([axes[0][1], axes[1][1], axes[2][1]]).normalize(),
      up([axes[0][2], axes[1][2], axes[2][2]]).normalize(),
    )
    ellipsoid.quaternion.setFromRotationMatrix(basis)
    ellipsoid.scale.set(Math.max(scene.fire.radii[0], 0.05), Math.max(scene.fire.radii[1], 0.05), Math.max(scene.fire.radii[2], 0.05))
    ellipsoid.position.copy(fire.position)
    dynamic.add(ellipsoid)
  }
  const origin = up(scene.gimbal.origin.length ? scene.gimbal.origin : scene.gimbal.p0)
  const mount = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.08, 0.16, 12), material(0x8d97a1, 0.35))
  mount.position.copy(up(scene.gimbal.p0))
  mount.castShadow = true
  dynamic.add(mount)
  const direction = up(scene.gimbal.direction)
  if (direction.lengthSq() > 0) {
    const tip = origin.clone().add(direction.normalize().multiplyScalar(scene.gimbal.laser ? 1.4 : 0.35))
    dynamic.add(line([origin, tip], scene.gimbal.laser ? 0xb64038 : 0x8d97a1))
  }
  if (scene.jet.length > 1) {
    const tube = new THREE.Mesh(
      new THREE.TubeGeometry(new THREE.CatmullRomCurve3(scene.jet.map(up)), scene.jet.length * 2, 0.012, 6, false),
      material(0x7ea3b5, 0.42),
    )
    dynamic.add(tube)
  }
  const spread = scene.spread
  if (spread && spread.status === "ESTIMATED") {
    polygon(spread.now, 0xd4652f, 0.03)
    polygon(spread.horizon_30s, 0xc6a15b, 0.035)
    polygon(spread.horizon_60s, 0x5d7384, 0.04)
  }
}

function resize() {
  if (!renderer || !camera || !host.value) return
  const width = host.value.clientWidth
  const height = host.value.clientHeight
  if (width < 2 || height < 2) return
  renderer.setSize(width, height, false)
  camera.aspect = width / height
  camera.updateProjectionMatrix()
}

function animate() {
  frame = requestAnimationFrame(animate)
  if (!props.still && controls && camera && !dragging && performance.now() > resumeAt) {
    const offset = camera.position.clone().sub(controls.target)
    const yaw = Math.atan2(offset.x, offset.z) + 0.0016
    const radius = Math.hypot(offset.x, offset.z)
    camera.position.x = controls.target.x + Math.sin(yaw) * radius
    camera.position.z = controls.target.z + Math.cos(yaw) * radius
    controls.update()
  }
  renderer?.render(world, camera as THREE.PerspectiveCamera)
}

let built = false
watch(
  () => props.scene,
  (scene) => {
    if (!scene || !renderer) return
    if (!built) {
      buildRoom(scene)
      built = true
    }
    refresh(scene)
  },
)

onMounted(() => {
  const element = host.value
  if (!element) return
  renderer = new THREE.WebGLRenderer({ antialias: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5))
  renderer.setClearColor(0x101418)
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.PCFSoftShadowMap
  element.appendChild(renderer.domElement)
  camera = new THREE.PerspectiveCamera(38, 1, 0.1, 80)
  controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.dampingFactor = 0.08
  controls.maxPolarAngle = Math.PI * 0.48
  controls.addEventListener("start", () => {
    dragging = true
  })
  controls.addEventListener("end", () => {
    dragging = false
    resumeAt = performance.now() + 4000
  })
  world.add(new THREE.HemisphereLight(0xf4f1ea, 0x2a3038, 0.85))
  const sun = new THREE.DirectionalLight(0xfff6ea, 1.15)
  sun.position.set(2, 9, 3)
  sun.castShadow = true
  sun.shadow.mapSize.set(1024, 1024)
  world.add(sun)
  world.add(root)
  world.add(dynamic)
  resize()
  if (props.scene) {
    buildRoom(props.scene)
    built = true
    refresh(props.scene)
  }
  window.addEventListener("resize", resize)
  animate()
})

onBeforeUnmount(() => {
  cancelAnimationFrame(frame)
  window.removeEventListener("resize", resize)
  controls?.dispose()
  renderer?.dispose()
  renderer?.domElement.remove()
})
</script>

<template>
  <div ref="host" class="twin-host" />
</template>
