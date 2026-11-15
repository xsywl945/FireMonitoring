<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { ElMessage } from "element-plus"
import { api, currentRole } from "../api/client"
import type { AlertEventRow, Room } from "../api/types"
import { eventLabels, messageOf } from "../labels"

interface Actuator {
  pump: string
  laser: string
  latch: string
  pan: number
  tilt: number
  heartbeat: boolean
}

interface SuppressionState {
  phase: string | null
  block: string | null
  message: string | null
  cover_probability: number | null
  cover_threshold: number
  web_estop: boolean
  actuator: Actuator
  events: AlertEventRow[]
}

const rooms = ref<Room[]>([])
const roomId = ref<number | null>(null)
const state = ref<SuppressionState | null>(null)
const pan = ref(0)
const tilt = ref(0)
const p0 = ref("0,0,2.2")
const yaw = ref(0)
const samples = ref("")
const residuals = ref<number[] | null>(null)
const admin = currentRole() === "admin"
let timer = 0

const latchText = computed(() => {
  const latch = state.value?.actuator.latch
  if (latch === "LATCHED") return "锁定"
  if (latch === "ARMED") return "待解锁"
  if (state.value?.web_estop) return "网页急停"
  return "未锁定"
})

async function loadRooms() {
  rooms.value = await api<Room[]>("/rooms")
  if (roomId.value === null && rooms.value.length) roomId.value = rooms.value[0].id
}

async function load() {
  if (!roomId.value) {
    state.value = null
    return
  }
  state.value = await api<SuppressionState>(`/suppression?room_id=${roomId.value}`)
}

async function estop() {
  try {
    state.value = { ...(await api<SuppressionState>("/suppression/estop", { method: "POST" })), events: state.value?.events ?? [] }
    await load()
    ElMessage.warning("已急停")
  } catch (error) {
    ElMessage.error(messageOf(error))
  }
}

async function unlock() {
  try {
    await api("/suppression/unlock", { method: "POST" })
    await load()
  } catch (error) {
    ElMessage.error(messageOf(error))
  }
}

async function aim() {
  try {
    await api("/suppression/aim", {
      method: "POST",
      body: JSON.stringify({ pan_cdeg: pan.value, tilt_cdeg: tilt.value }),
    })
    await load()
  } catch (error) {
    ElMessage.error(messageOf(error))
  }
}

async function spray() {
  if (!roomId.value) return
  try {
    await api("/suppression/spray", {
      method: "POST",
      body: JSON.stringify({ room_id: roomId.value }),
    })
    await load()
  } catch (error) {
    ElMessage.error(messageOf(error))
  }
}

async function calibrate() {
  try {
    const parsed = JSON.parse(samples.value) as { pan_cdeg: number; tilt_cdeg: number; xyz: number[] }[]
    const [x, y, z] = p0.value.split(",").map((item) => Number(item.trim()))
    const result = await api<{ residuals_m: number[] }>("/suppression/calibrate", {
      method: "POST",
      body: JSON.stringify({
        p0: [x, y, z],
        yaw_deg: yaw.value,
        samples: parsed,
      }),
    })
    residuals.value = result.residuals_m
    ElMessage.success("标定完成")
  } catch (error) {
    ElMessage.error(messageOf(error))
  }
}

onMounted(async () => {
  await loadRooms()
  await load()
  timer = window.setInterval(load, 2000)
})
onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <div class="stack">
    <div class="panel toolbar">
      <el-select v-model="roomId" placeholder="选择教室" style="width: 240px" @change="load">
        <el-option v-for="room in rooms" :key="room.id" :label="room.name" :value="room.id" />
      </el-select>
      <div>
        <el-button type="danger" @click="estop">网页急停</el-button>
        <el-button v-if="admin" @click="unlock">解锁</el-button>
      </div>
    </div>
    <div v-if="state" class="panel">
      <div class="toolbar"><strong>云台</strong></div>
      <p>状态 {{ state.phase || "监视" }}<span v-if="state.message">，{{ state.message }}</span></p>
      <p>
        水平 {{ state.actuator.pan }} 百分度，俯仰 {{ state.actuator.tilt }} 百分度，
        激光 {{ state.actuator.laser === "ON" ? "开" : "关" }}，
        泵 {{ state.actuator.pump }}，
        锁 {{ latchText }}，
        心跳 {{ state.actuator.heartbeat ? "正常" : "中断" }}
      </p>
      <p v-if="state.cover_probability !== null">
        覆盖概率 {{ state.cover_probability.toFixed(2) }}，阈值 {{ state.cover_threshold }}
      </p>
    </div>
    <div v-if="state" class="panel">
      <div class="toolbar"><strong>事件</strong></div>
      <el-timeline v-if="state.events.length">
        <el-timeline-item v-for="item in state.events" :key="item.id" :timestamp="item.occurred_at">
          {{ eventLabels[item.kind] || item.kind }}
          <span v-if="typeof item.detail.phase === 'string'"> {{ item.detail.phase }}</span>
          <span v-if="typeof item.detail.message === 'string'"> {{ item.detail.message }}</span>
        </el-timeline-item>
      </el-timeline>
      <p v-else>暂无事件</p>
    </div>
    <div v-if="admin" class="panel">
      <div class="toolbar"><strong>手动操作</strong></div>
      <p>急停和禁水不能绕过。手动喷水仍检查定位、人员、心跳和冷却。</p>
      <div class="form-grid">
        <el-input-number v-model="pan" :min="-12000" :max="12000" />
        <el-input-number v-model="tilt" :min="0" :max="6000" />
        <div>
          <el-button @click="aim">瞄准</el-button>
          <el-button type="danger" @click="spray">喷水</el-button>
        </div>
      </div>
    </div>
    <div v-if="admin" class="panel">
      <div class="toolbar"><strong>激光自标定</strong></div>
      <p>只填写粗略量到的云台位置。样本为 15 到 20 组水平、俯仰和三角化坐标，单位是百分度和米。</p>
      <div class="form-grid">
        <el-input v-model="p0" placeholder="x,y,z" />
        <el-input-number v-model="yaw" />
      </div>
      <el-input v-model="samples" type="textarea" :rows="6" placeholder='[{"pan_cdeg":0,"tilt_cdeg":1500,"xyz":[1,2,1]}]' />
      <el-button style="margin-top: 12px" @click="calibrate">拟合</el-button>
      <p v-if="residuals">各点残差（米）：{{ residuals.map((item) => item.toFixed(4)).join("，") }}</p>
    </div>
  </div>
</template>
