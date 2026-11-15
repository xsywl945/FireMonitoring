<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { ElMessage } from "element-plus"
import StreamCell from "../components/StreamCell.vue"
import ReplayPane from "../components/ReplayPane.vue"
import { api, fetchAuthorized } from "../api/client"
import { loadDemoMode } from "../demo"
import type { DemoCamera, DemoStatus } from "../demo"
import type { LiveCamera, LiveState, PumpStatus, Room } from "../api/types"
import { messageOf } from "../labels"

const rooms = ref<Room[]>([])
const roomId = ref<number | null>(null)
const live = ref<LiveState | null>(null)
const pump = ref<PumpStatus | null>(null)
const replay = ref(false)
const demo = ref<DemoStatus | null>(null)
const urls = ref<Record<number, string>>({})
let timer = 0

const cells = computed<(LiveCamera | null)[]>(() => {
  const bySlot = new Map((live.value?.cameras ?? []).map((item) => [item.slot, item]))
  return [1, 2, 3, 4].map((slot) => bySlot.get(slot) ?? null)
})

const replayCells = computed<(DemoCamera | null)[]>(() => {
  const bySlot = new Map((demo.value?.cameras ?? []).map((item) => [item.slot, item]))
  return [1, 2, 3, 4].map((slot) => bySlot.get(slot) ?? null)
})

async function loadRooms() {
  rooms.value = await api<Room[]>("/rooms")
}

async function loadLive() {
  if (!roomId.value) {
    live.value = null
    return
  }
  try {
    live.value = await api<LiveState>(`/rooms/${roomId.value}/live`)
  } catch (error) {
    ElMessage.error(messageOf(error))
  }
}

async function loadPump() {
  pump.value = await api<PumpStatus>("/pump")
}

async function stopPump() {
  try {
    pump.value = await api<PumpStatus>("/pump/stop", { method: "POST" })
  } catch (error) {
    ElMessage.error(messageOf(error))
  }
}

watch(roomId, () => {
  window.clearInterval(timer)
  loadLive()
  if (roomId.value) timer = window.setInterval(loadLive, 500)
})

async function loadReplay() {
  demo.value = await api<DemoStatus>("/demo")
  for (const camera of demo.value.cameras) {
    try {
      const blob = await fetchAuthorized(`/demo/frames/${camera.id}`)
      const next = URL.createObjectURL(blob)
      const previous = urls.value[camera.id]
      urls.value = { ...urls.value, [camera.id]: next }
      if (previous) URL.revokeObjectURL(previous)
    } catch {
      // 回放尚未出画。
    }
  }
}

onMounted(async () => {
  const mode = await loadDemoMode()
  replay.value = mode.enabled
  await loadRooms()
  await loadPump()
  if (replay.value) {
    await loadReplay()
    timer = window.setInterval(() => void loadReplay(), 400)
  }
})

onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <div class="stack">
    <div class="panel toolbar">
      <el-select v-model="roomId" placeholder="选择教室" style="width: 240px" clearable>
        <el-option v-for="room in rooms" :key="room.id" :label="room.name" :value="room.id" />
      </el-select>
      <div>
        <span v-if="pump">泵 {{ pump.enabled ? pump.deviceState : "未启用" }}</span>
        <el-button style="margin-left: 12px" @click="stopPump">紧急停泵</el-button>
      </div>
    </div>
    <p v-if="replay" class="panel">当前画面是录像回放，不是实况。</p>
    <div v-if="replay" class="monitor-grid">
      <ReplayPane
        v-for="(camera, index) in replayCells"
        :key="index"
        :camera="camera"
        :src="camera ? urls[camera.id] || '' : ''"
      />
    </div>
    <div v-else class="monitor-grid">
      <StreamCell v-for="(camera, index) in cells" :key="index" :camera="camera" />
    </div>
  </div>
</template>
