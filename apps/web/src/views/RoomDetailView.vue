<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue"
import { useRoute } from "vue-router"
import { ElMessage } from "element-plus"
import FloorPlan from "../components/FloorPlan.vue"
import { api, currentRole, download, fetchAuthorized } from "../api/client"
import type { BoundCamera, Calibration, Camera, LiveState, Room } from "../api/types"
import { calibrationStatus, healthLabels, messageOf, px } from "../labels"

interface HeldFrame {
  name: string
  blob: Blob
  url: string
}

interface MarkerRow {
  marker_id: number
  pixel: number[]
  x: number | null
  y: number | null
  z: number | null
}

const route = useRoute()
const id = computed(() => Number(route.params.id))
const admin = currentRole() === "admin"
const room = ref<Room | null>(null)
const cameras = ref<Camera[]>([])
const allRooms = ref<Room[]>([])
const slots = ref<(number | null)[]>([null, null, null, null])
const selectedId = ref<number | null>(null)
const paper = ref<"a4" | "a3">("a4")
const intrinsicFrames = ref<HeldFrame[]>([])
const extrinsicFrame = ref<HeldFrame | null>(null)
const markers = ref<MarkerRow[]>([])
const busy = ref(false)
const health = ref<Record<number, string>>({})
const plan = reactive({ originX: 0, originY: 0, meters: 0.01, worldX: 0, worldY: 0 })
const file = ref<File | null>(null)
let timer = 0
const drafting = ref(false)
const draftName = ref("课桌区")
const draftPoints = ref<number[][]>([])

const regionShapes = computed(() => {
  const saved = (room.value?.floor_plan?.combustibles ?? []).map((item) => ({
    points: item.polygon,
    stroke: "#1e3a5f",
    fill: "rgba(30, 58, 95, 0.12)",
  }))
  if (draftPoints.value.length < 2) return saved
  return [...saved, { points: draftPoints.value, stroke: "#9f2d20", fill: "rgba(159, 45, 32, 0.2)" }]
})

const options = computed(() => {
  const used = new Set<number>()
  for (const item of allRooms.value) {
    if (item.id === id.value) continue
    for (const camera of item.cameras) used.add(camera.camera_id)
  }
  return cameras.value.filter((camera) => !used.has(camera.id) || slots.value.includes(camera.id))
})

const selected = computed(() => cameras.value.find((item) => item.id === selectedId.value) ?? null)

function calibrationOf(cameraId: number): Calibration | null {
  return cameras.value.find((item) => item.id === cameraId)?.calibration ?? null
}

async function load() {
  room.value = await api<Room>(`/rooms/${id.value}`)
  cameras.value = await api<Camera[]>("/cameras")
  allRooms.value = await api<Room[]>("/rooms")
  slots.value = [null, null, null, null]
  for (const item of room.value.cameras) slots.value[item.slot - 1] = item.camera_id
  const current = room.value.floor_plan
  if (current) {
    plan.originX = current.origin_px[0] ?? 0
    plan.originY = current.origin_px[1] ?? 0
    plan.meters = current.meters_per_pixel
    plan.worldX = current.origin_world_m[0] ?? 0
    plan.worldY = current.origin_world_m[1] ?? 0
  }
}

async function loadHealth() {
  const state = await api<LiveState>(`/rooms/${id.value}/live`)
  const next: Record<number, string> = {}
  for (const camera of state.cameras) next[camera.camera_id] = camera.health
  health.value = next
}

function clearFrames() {
  for (const item of intrinsicFrames.value) URL.revokeObjectURL(item.url)
  intrinsicFrames.value = []
  if (extrinsicFrame.value) URL.revokeObjectURL(extrinsicFrame.value.url)
  extrinsicFrame.value = null
  markers.value = []
}

function openCalibration(cameraId: number) {
  selectedId.value = cameraId
  const board = calibrationOf(cameraId)?.board
  if (board === "a4" || board === "a3") paper.value = board
  clearFrames()
}

async function saveBindings() {
  try {
    room.value = await api<Room>(`/rooms/${id.value}/cameras`, {
      method: "PUT",
      body: JSON.stringify({ camera_ids: slots.value }),
    })
    ElMessage.success("已保存")
  } catch (error) {
    ElMessage.error(messageOf(error))
  }
}

async function savePdf(kind: "charuco" | "markers", size: "a4" | "a3") {
  try {
    await download(`/calibration/boards/${kind}?paper=${size}`, `${kind}-${size}.pdf`)
  } catch (error) {
    ElMessage.error(messageOf(error))
  }
}

function onIntrinsicFiles(event: Event) {
  const input = event.target as HTMLInputElement
  const files = input.files
  if (!files) return
  for (const item of files) {
    intrinsicFrames.value.push({ name: item.name, blob: item, url: URL.createObjectURL(item) })
  }
  input.value = ""
}

function onExtrinsicFile(event: Event) {
  const input = event.target as HTMLInputElement
  const item = input.files?.[0]
  if (!item) return
  if (extrinsicFrame.value) URL.revokeObjectURL(extrinsicFrame.value.url)
  extrinsicFrame.value = { name: item.name, blob: item, url: URL.createObjectURL(item) }
  markers.value = []
  input.value = ""
}

async function grab(target: "intrinsics" | "extrinsics") {
  if (selectedId.value === null) return
  try {
    const blob = await fetchAuthorized(`/cameras/${selectedId.value}/frame`)
    const url = URL.createObjectURL(blob)
    if (target === "intrinsics") {
      intrinsicFrames.value.push({ name: `frame-${Date.now()}.png`, blob, url })
      return
    }
    if (extrinsicFrame.value) URL.revokeObjectURL(extrinsicFrame.value.url)
    extrinsicFrame.value = { name: `frame-${Date.now()}.png`, blob, url }
    markers.value = []
  } catch (error) {
    ElMessage.error(messageOf(error))
  }
}

async function runIntrinsics() {
  if (selectedId.value === null) return
  const body = new FormData()
  body.set("paper", paper.value)
  for (const item of intrinsicFrames.value) body.append("files", item.blob, item.name)
  busy.value = true
  try {
    await api(`/cameras/${selectedId.value}/calibration/intrinsics`, { method: "POST", body })
    ElMessage.success("内参已写入")
    clearFrames()
    await load()
  } catch (error) {
    ElMessage.error(messageOf(error))
  } finally {
    busy.value = false
  }
}

async function detectMarkers() {
  if (selectedId.value === null || !extrinsicFrame.value) return
  const body = new FormData()
  body.set("file", extrinsicFrame.value.blob, extrinsicFrame.value.name)
  busy.value = true
  try {
    const found = await api<{ markers: { marker_id: number; pixel: number[] }[] }>(
      `/cameras/${selectedId.value}/calibration/detect`,
      { method: "POST", body },
    )
    markers.value = found.markers.map((item) => ({
      marker_id: item.marker_id,
      pixel: item.pixel,
      x: null,
      y: null,
      z: null,
    }))
  } catch (error) {
    ElMessage.error(messageOf(error))
  } finally {
    busy.value = false
  }
}

async function saveExtrinsics() {
  if (selectedId.value === null || !extrinsicFrame.value) return
  if (markers.value.some((item) => item.x === null || item.y === null || item.z === null)) {
    ElMessage.error("每个控制点都要填教室坐标")
    return
  }
  const body = new FormData()
  body.set("file", extrinsicFrame.value.blob, extrinsicFrame.value.name)
  body.set(
    "points",
    JSON.stringify(
      markers.value.map((item) => ({
        marker_id: item.marker_id,
        world_m: [item.x, item.y, item.z],
      })),
    ),
  )
  busy.value = true
  try {
    await api(`/cameras/${selectedId.value}/calibration/extrinsics`, { method: "POST", body })
    ElMessage.success("外参已写入")
    await load()
  } catch (error) {
    ElMessage.error(messageOf(error))
  } finally {
    busy.value = false
  }
}

function dropIntrinsic(index: number) {
  URL.revokeObjectURL(intrinsicFrames.value[index].url)
  intrinsicFrames.value.splice(index, 1)
}

function onFile(event: Event) {
  const input = event.target as HTMLInputElement
  file.value = input.files?.[0] ?? null
}

async function savePlan() {
  if (!file.value) {
    ElMessage.error("请选择平面图")
    return
  }
  const body = new FormData()
  body.set("file", file.value)
  body.set("origin_x", String(plan.originX))
  body.set("origin_y", String(plan.originY))
  body.set("meters_per_pixel", String(plan.meters))
  body.set("world_x", String(plan.worldX))
  body.set("world_y", String(plan.worldY))
  try {
    room.value = await api<Room>(`/rooms/${id.value}/floor-plan`, { method: "POST", body })
    ElMessage.success("已保存")
  } catch (error) {
    ElMessage.error(messageOf(error))
  }
}

function onPick(point: number[]) {
  if (!drafting.value) return
  draftPoints.value = [...draftPoints.value, point]
}

async function saveRegion() {
  if (!draftName.value.trim()) {
    ElMessage.error("填写区域名称")
    return
  }
  if (draftPoints.value.length < 3) {
    ElMessage.error("至少三个顶点")
    return
  }
  const current = room.value?.floor_plan?.combustibles ?? []
  const regions = [...current, { name: draftName.value.trim(), polygon: draftPoints.value }]
  try {
    room.value = await api<Room>(`/rooms/${id.value}/combustibles`, {
      method: "PUT",
      body: JSON.stringify({ regions }),
    })
    draftPoints.value = []
    drafting.value = false
  } catch (error) {
    ElMessage.error(messageOf(error))
  }
}

async function removeRegion(index: number) {
  const current = room.value?.floor_plan?.combustibles ?? []
  const regions = current.filter((_, item) => item !== index)
  try {
    room.value = await api<Room>(`/rooms/${id.value}/combustibles`, {
      method: "PUT",
      body: JSON.stringify({ regions }),
    })
  } catch (error) {
    ElMessage.error(messageOf(error))
  }
}

function rowClass({ row }: { row: BoundCamera }) {
  return row.calibrated ? "" : "row-uncalibrated"
}

watch(
  id,
  () => {
    window.clearInterval(timer)
    selectedId.value = null
    clearFrames()
    load()
    loadHealth()
    timer = window.setInterval(loadHealth, 1000)
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  window.clearInterval(timer)
  clearFrames()
})
</script>

<template>
  <div v-if="room" class="stack">
    <div class="panel">
      <div class="toolbar"><strong>{{ room.name }}</strong></div>
      <div class="form-grid">
        <el-select v-for="slot in 4" :key="slot" v-model="slots[slot - 1]" clearable :placeholder="`第 ${slot} 路`">
          <el-option v-for="camera in options" :key="camera.id" :label="camera.name" :value="camera.id" />
        </el-select>
      </div>
      <el-button v-if="admin" type="primary" style="margin-top: 12px" @click="saveBindings">保存绑定</el-button>
    </div>
    <div class="panel">
      <div class="toolbar"><strong>标定</strong></div>
      <el-table :data="room.cameras" :row-class-name="rowClass" border>
        <el-table-column prop="slot" label="路" width="60" />
        <el-table-column prop="name" label="摄像头" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">{{ calibrationStatus(calibrationOf(row.camera_id)) }}</template>
        </el-table-column>
        <el-table-column label="内参误差" width="120">
          <template #default="{ row }">{{ px(calibrationOf(row.camera_id)?.intrinsics_reprojection_error_px) }}</template>
        </el-table-column>
        <el-table-column label="外参误差" width="120">
          <template #default="{ row }">{{ px(calibrationOf(row.camera_id)?.extrinsics_reprojection_error_px) }}</template>
        </el-table-column>
        <el-table-column label="画面" width="110">
          <template #default="{ row }">{{ healthLabels[health[row.camera_id]] || "离线" }}</template>
        </el-table-column>
        <el-table-column v-if="admin" label="操作" width="90">
          <template #default="{ row }">
            <el-button link type="primary" @click="openCalibration(row.camera_id)">标定</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="admin && selected" class="calibration-work">
        <div class="toolbar">
          <strong>{{ selected.name }}</strong>
          <span>内参 {{ px(selected.calibration?.intrinsics_reprojection_error_px) }}，外参 {{ px(selected.calibration?.extrinsics_reprojection_error_px) }}</span>
        </div>
        <div class="downloads">
          <el-button @click="savePdf('charuco', 'a4')">下载 ChArUco A4</el-button>
          <el-button @click="savePdf('charuco', 'a3')">下载 ChArUco A3</el-button>
          <el-button @click="savePdf('markers', 'a4')">下载控制点 A4</el-button>
          <el-button @click="savePdf('markers', 'a3')">下载控制点 A3</el-button>
        </div>
        <div class="section">
          <div class="toolbar"><strong>内参</strong></div>
          <div class="row">
            <span>拍摄用的板</span>
            <el-select v-model="paper" style="width: 120px">
              <el-option label="A4" value="a4" />
              <el-option label="A3" value="a3" />
            </el-select>
            <input type="file" accept="image/*" multiple @change="onIntrinsicFiles" />
            <el-button @click="grab('intrinsics')">抓取当前画面</el-button>
            <el-button type="primary" :disabled="busy" @click="runIntrinsics">标定内参（{{ intrinsicFrames.length }} 张）</el-button>
          </div>
          <div v-if="intrinsicFrames.length" class="thumbs">
            <figure v-for="(item, index) in intrinsicFrames" :key="item.url">
              <img :src="item.url" alt="" />
              <el-button link type="danger" @click="dropIntrinsic(index)">去掉</el-button>
            </figure>
          </div>
        </div>
        <div class="section">
          <div class="toolbar"><strong>外参</strong></div>
          <div class="row">
            <input type="file" accept="image/*" @change="onExtrinsicFile" />
            <el-button @click="grab('extrinsics')">抓取当前画面</el-button>
            <el-button type="primary" :disabled="busy || !extrinsicFrame" @click="detectMarkers">检测控制点</el-button>
          </div>
          <img v-if="extrinsicFrame" class="preview" :src="extrinsicFrame.url" alt="" />
          <el-table v-if="markers.length" :data="markers" border>
            <el-table-column prop="marker_id" label="编号" width="80" />
            <el-table-column label="像素 u" width="120">
              <template #default="{ row }">{{ row.pixel[0].toFixed(1) }}</template>
            </el-table-column>
            <el-table-column label="像素 v" width="120">
              <template #default="{ row }">{{ row.pixel[1].toFixed(1) }}</template>
            </el-table-column>
            <el-table-column label="教室 X（米）">
              <template #default="{ row }"><el-input-number v-model="row.x" :controls="false" /></template>
            </el-table-column>
            <el-table-column label="教室 Y（米）">
              <template #default="{ row }"><el-input-number v-model="row.y" :controls="false" /></template>
            </el-table-column>
            <el-table-column label="教室 Z（米）">
              <template #default="{ row }"><el-input-number v-model="row.z" :controls="false" /></template>
            </el-table-column>
          </el-table>
          <el-button v-if="markers.length" type="primary" style="margin-top: 12px" :disabled="busy" @click="saveExtrinsics">保存外参</el-button>
        </div>
      </div>
    </div>
    <div class="panel">
      <div class="toolbar"><strong>平面图</strong></div>
      <FloorPlan
        v-if="room.floor_plan"
        :room-id="room.id"
        :plan="room.floor_plan"
        :position="null"
        :shapes="regionShapes"
        :picking="drafting"
        @pick="onPick"
      />
      <div v-if="admin" class="form-grid" style="margin-top: 12px">
        <el-form-item label="原点像素 X"><el-input-number v-model="plan.originX" :controls="false" /></el-form-item>
        <el-form-item label="原点像素 Y"><el-input-number v-model="plan.originY" :controls="false" /></el-form-item>
        <el-form-item label="米/像素"><el-input-number v-model="plan.meters" :controls="false" :step="0.01" /></el-form-item>
        <el-form-item label="原点世界 X"><el-input-number v-model="plan.worldX" :controls="false" /></el-form-item>
        <el-form-item label="原点世界 Y"><el-input-number v-model="plan.worldY" :controls="false" /></el-form-item>
        <el-form-item label="图片"><input type="file" accept="image/*" @change="onFile" /></el-form-item>
      </div>
      <el-button v-if="admin" type="primary" @click="savePlan">保存平面图</el-button>
      <div v-if="admin && room.floor_plan" style="margin-top: 16px">
        <div class="toolbar"><strong>可燃物区域</strong></div>
        <el-table :data="room.floor_plan.combustibles" border>
          <el-table-column prop="name" label="名称" />
          <el-table-column label="顶点数" width="100">
            <template #default="{ row }">{{ row.polygon.length }}</template>
          </el-table-column>
          <el-table-column label="操作" width="100">
            <template #default="{ $index }">
              <el-button link type="danger" @click="removeRegion($index)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div style="display: flex; gap: 8px; margin-top: 12px">
          <el-input v-model="draftName" placeholder="课桌区、试剂柜" style="max-width: 200px" />
          <el-button @click="drafting = !drafting">{{ drafting ? "结束圈选" : "在图上圈选" }}</el-button>
          <el-button type="primary" @click="saveRegion">保存区域</el-button>
          <span v-if="draftPoints.length">已点 {{ draftPoints.length }} 个顶点</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
:deep(.row-uncalibrated) {
  --el-table-tr-bg-color: #fde8e8;
  color: #b42318;
}

.calibration-work {
  margin-top: 16px;
}

.downloads,
.row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.section {
  margin-top: 16px;
}

.thumbs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.thumbs figure {
  margin: 0;
  width: 96px;
}

.thumbs img,
.preview {
  display: block;
  width: 160px;
  max-width: 100%;
  background: #111;
}

.thumbs img {
  width: 96px;
  height: 64px;
  object-fit: cover;
}
</style>
