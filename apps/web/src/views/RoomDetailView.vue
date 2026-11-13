<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue"
import { useRoute } from "vue-router"
import { ElMessage } from "element-plus"
import FloorPlan from "../components/FloorPlan.vue"
import { api, currentRole } from "../api/client"
import type { Camera, Room } from "../api/types"
import { messageOf } from "../labels"

interface LandmarkForm {
  x: number
  y: number
  z: number
  u: number
  v: number
}

const route = useRoute()
const id = computed(() => Number(route.params.id))
const admin = currentRole() === "admin"
const room = ref<Room | null>(null)
const cameras = ref<Camera[]>([])
const allRooms = ref<Room[]>([])
const slots = ref<(number | null)[]>([null, null, null, null])
const editingId = ref<number | null>(null)
const calibration = reactive({
  fx: 0,
  fy: 0,
  cx: 0,
  cy: 0,
  k1: 0,
  k2: 0,
  p1: 0,
  p2: 0,
  k3: 0,
  landmarks: [] as LandmarkForm[],
})
const plan = reactive({ originX: 0, originY: 0, meters: 0.01, worldX: 0, worldY: 0 })
const file = ref<File | null>(null)

const options = computed(() => {
  const used = new Set<number>()
  for (const item of allRooms.value) {
    if (item.id === id.value) continue
    for (const camera of item.cameras) used.add(camera.camera_id)
  }
  return cameras.value.filter((camera) => !used.has(camera.id) || slots.value.includes(camera.id))
})

function blankLandmarks(): LandmarkForm[] {
  return [0, 1, 2, 3].map(() => ({ x: 0, y: 0, z: 0, u: 0, v: 0 }))
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

function editCalibration(cameraId: number) {
  editingId.value = cameraId
  const current = cameras.value.find((item) => item.id === cameraId)?.calibration
  if (!current) {
    calibration.fx = 0
    calibration.fy = 0
    calibration.cx = 0
    calibration.cy = 0
    calibration.k1 = 0
    calibration.k2 = 0
    calibration.p1 = 0
    calibration.p2 = 0
    calibration.k3 = 0
    calibration.landmarks = blankLandmarks()
    return
  }
  calibration.fx = current.intrinsics[0]?.[0] ?? 0
  calibration.fy = current.intrinsics[1]?.[1] ?? 0
  calibration.cx = current.intrinsics[0]?.[2] ?? 0
  calibration.cy = current.intrinsics[1]?.[2] ?? 0
  calibration.k1 = current.distortion[0] ?? 0
  calibration.k2 = current.distortion[1] ?? 0
  calibration.p1 = current.distortion[2] ?? 0
  calibration.p2 = current.distortion[3] ?? 0
  calibration.k3 = current.distortion[4] ?? 0
  calibration.landmarks = current.landmarks.map((item) => ({
    x: item.world_m[0] ?? 0,
    y: item.world_m[1] ?? 0,
    z: item.world_m[2] ?? 0,
    u: item.pixel[0] ?? 0,
    v: item.pixel[1] ?? 0,
  }))
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

async function saveCalibration() {
  if (editingId.value === null) return
  const body = {
    intrinsics: [
      [calibration.fx, 0, calibration.cx],
      [0, calibration.fy, calibration.cy],
      [0, 0, 1],
    ],
    distortion: [calibration.k1, calibration.k2, calibration.p1, calibration.p2, calibration.k3],
    landmarks: calibration.landmarks.map((item) => ({
      world_m: [item.x, item.y, item.z],
      pixel: [item.u, item.v],
    })),
  }
  try {
    await api(`/cameras/${editingId.value}/calibration`, {
      method: "PUT",
      body: JSON.stringify(body),
    })
    ElMessage.success("已保存")
    await load()
  } catch (error) {
    ElMessage.error(messageOf(error))
  }
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

watch(id, load, { immediate: true })
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
      <el-table :data="room.cameras" border>
        <el-table-column prop="slot" label="路" width="80" />
        <el-table-column prop="name" label="摄像头" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">{{ row.calibrated ? "已录入" : "未录入" }}</template>
        </el-table-column>
        <el-table-column v-if="admin" label="操作" width="100">
          <template #default="{ row }">
            <el-button link type="primary" @click="editCalibration(row.camera_id)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="admin && editingId !== null" style="margin-top: 16px">
        <div class="form-grid">
          <el-form-item label="fx"><el-input-number v-model="calibration.fx" :controls="false" /></el-form-item>
          <el-form-item label="fy"><el-input-number v-model="calibration.fy" :controls="false" /></el-form-item>
          <el-form-item label="cx"><el-input-number v-model="calibration.cx" :controls="false" /></el-form-item>
          <el-form-item label="cy"><el-input-number v-model="calibration.cy" :controls="false" /></el-form-item>
          <el-form-item label="k1"><el-input-number v-model="calibration.k1" :controls="false" /></el-form-item>
          <el-form-item label="k2"><el-input-number v-model="calibration.k2" :controls="false" /></el-form-item>
          <el-form-item label="p1"><el-input-number v-model="calibration.p1" :controls="false" /></el-form-item>
          <el-form-item label="p2"><el-input-number v-model="calibration.p2" :controls="false" /></el-form-item>
          <el-form-item label="k3"><el-input-number v-model="calibration.k3" :controls="false" /></el-form-item>
        </div>
        <el-table :data="calibration.landmarks" border>
          <el-table-column label="世界 X"><template #default="{ row }"><el-input-number v-model="row.x" :controls="false" /></template></el-table-column>
          <el-table-column label="世界 Y"><template #default="{ row }"><el-input-number v-model="row.y" :controls="false" /></template></el-table-column>
          <el-table-column label="世界 Z"><template #default="{ row }"><el-input-number v-model="row.z" :controls="false" /></template></el-table-column>
          <el-table-column label="像素 u"><template #default="{ row }"><el-input-number v-model="row.u" :controls="false" /></template></el-table-column>
          <el-table-column label="像素 v"><template #default="{ row }"><el-input-number v-model="row.v" :controls="false" /></template></el-table-column>
          <el-table-column label="" width="80">
            <template #default="{ $index }"><el-button link type="danger" @click="calibration.landmarks.splice($index, 1)">删除</el-button></template>
          </el-table-column>
        </el-table>
        <div style="margin-top: 12px">
          <el-button @click="calibration.landmarks.push({ x: 0, y: 0, z: 0, u: 0, v: 0 })">增加控制点</el-button>
          <el-button type="primary" @click="saveCalibration">保存标定</el-button>
        </div>
      </div>
    </div>
    <div class="panel">
      <div class="toolbar"><strong>平面图</strong></div>
      <FloorPlan v-if="room.floor_plan" :room-id="room.id" :plan="room.floor_plan" :position="null" />
      <div v-if="admin" class="form-grid" style="margin-top: 12px">
        <el-form-item label="原点像素 X"><el-input-number v-model="plan.originX" :controls="false" /></el-form-item>
        <el-form-item label="原点像素 Y"><el-input-number v-model="plan.originY" :controls="false" /></el-form-item>
        <el-form-item label="米/像素"><el-input-number v-model="plan.meters" :controls="false" :step="0.01" /></el-form-item>
        <el-form-item label="原点世界 X"><el-input-number v-model="plan.worldX" :controls="false" /></el-form-item>
        <el-form-item label="原点世界 Y"><el-input-number v-model="plan.worldY" :controls="false" /></el-form-item>
        <el-form-item label="图片"><input type="file" accept="image/*" @change="onFile" /></el-form-item>
      </div>
      <el-button v-if="admin" type="primary" @click="savePlan">保存平面图</el-button>
    </div>
  </div>
</template>
