<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive, ref } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { api, currentRole } from "../api/client"
import type { Camera, CameraHealth, DeviceFault } from "../api/types"
import { calibrationStatus, faultLabels, formatTime, healthLabels, messageOf, px } from "../labels"

const admin = currentRole() === "admin"
const cameras = ref<Camera[]>([])
const health = ref<Record<number, string>>({})
const faults = ref<DeviceFault[]>([])
let timer = 0
const visible = ref(false)
const editing = ref<Camera | null>(null)
const form = reactive({
  name: "",
  source_type: "USB" as "USB" | "RTSP",
  source_uri: "",
  stream_key: "",
  fps: "",
})

async function load() {
  cameras.value = await api<Camera[]>("/cameras")
}

async function loadHealth() {
  const rows = await api<CameraHealth[]>("/cameras/health")
  const next: Record<number, string> = {}
  for (const row of rows) next[row.camera_id] = row.health
  health.value = next
  faults.value = await api<DeviceFault[]>("/cameras/faults")
}

function cameraName(cameraId: number) {
  return cameras.value.find((item) => item.id === cameraId)?.name || String(cameraId)
}

function openCreate() {
  editing.value = null
  form.name = ""
  form.source_type = "USB"
  form.source_uri = ""
  form.stream_key = ""
  form.fps = ""
  visible.value = true
}

function openEdit(row: Camera) {
  editing.value = row
  form.name = row.name
  form.source_type = row.source_type
  form.source_uri = row.source_uri
  form.stream_key = row.stream_key
  form.fps = String(row.target_fps)
  visible.value = true
}

async function save() {
  const body = JSON.stringify({
    name: form.name,
    source_type: form.source_type,
    source_uri: form.source_uri,
    stream_key: form.stream_key,
    target_fps: form.fps === "" ? null : Number(form.fps),
  })
  try {
    if (editing.value) {
      await api(`/cameras/${editing.value.id}`, { method: "PUT", body })
    } else {
      await api("/cameras", { method: "POST", body })
    }
    visible.value = false
    await load()
  } catch (error) {
    ElMessage.error(messageOf(error))
  }
}

async function remove(row: Camera) {
  try {
    await ElMessageBox.confirm(`删除摄像头 ${row.name}？`, "删除")
  } catch {
    return
  }
  try {
    await api(`/cameras/${row.id}`, { method: "DELETE" })
    await load()
  } catch (error) {
    ElMessage.error(messageOf(error))
  }
}

onMounted(async () => {
  await load()
  await loadHealth()
  timer = window.setInterval(loadHealth, 2000)
})
onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <div class="stack">
  <div class="panel">
    <div class="toolbar">
      <strong>摄像头</strong>
      <el-button v-if="admin" type="primary" @click="openCreate">新建</el-button>
    </div>
    <el-table :data="cameras" border>
      <el-table-column prop="name" label="名称" />
      <el-table-column label="类型" width="100">
        <template #default="{ row }">{{ row.source_type === "USB" ? "USB" : "网络" }}</template>
      </el-table-column>
      <el-table-column prop="source_uri" label="地址" />
      <el-table-column prop="stream_key" label="流标识" width="140" />
      <el-table-column prop="target_fps" label="帧率" width="80" />
      <el-table-column label="状态" width="120">
        <template #default="{ row }">{{ healthLabels[health[row.id]] || "离线" }}</template>
      </el-table-column>
      <el-table-column label="标定" min-width="180">
        <template #default="{ row }">
          {{ calibrationStatus(row.calibration) }}
          <template v-if="row.calibration">
            {{ px(row.calibration.intrinsics_reprojection_error_px) }}
            /
            {{ px(row.calibration.extrinsics_reprojection_error_px) }}
          </template>
        </template>
      </el-table-column>
      <el-table-column v-if="admin" label="操作" width="140">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-dialog v-model="visible" :title="editing ? '编辑摄像头' : '新建摄像头'" width="480px">
      <el-form label-position="top">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.source_type">
            <el-option label="USB" value="USB" />
            <el-option label="网络" value="RTSP" />
          </el-select>
        </el-form-item>
        <el-form-item :label="form.source_type === 'USB' ? 'DirectShow 设备名' : 'RTSP 地址'">
          <el-input v-model="form.source_uri" />
        </el-form-item>
        <el-form-item label="流标识"><el-input v-model="form.stream_key" /></el-form-item>
        <el-form-item label="帧率">
          <el-input v-model="form.fps" placeholder="留空使用配置默认值" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
  <div v-if="faults.length" class="panel">
    <div class="toolbar"><strong>设备故障</strong></div>
    <el-table :data="faults" border>
      <el-table-column label="时间" width="200">
        <template #default="{ row }">{{ formatTime(row.occurred_at) }}</template>
      </el-table-column>
      <el-table-column label="摄像头">
        <template #default="{ row }">{{ cameraName(row.camera_id) }}</template>
      </el-table-column>
      <el-table-column label="类型" width="140">
        <template #default="{ row }">{{ faultLabels[row.kind] || row.kind }}</template>
      </el-table-column>
    </el-table>
  </div>
  </div>
</template>
