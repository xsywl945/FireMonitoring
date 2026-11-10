<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { ElMessage } from "element-plus"
import StreamCell from "../components/StreamCell.vue"
import { api } from "../api/client"
import type { LiveCamera, LiveState, PumpStatus, Room } from "../api/types"
import { messageOf } from "../labels"

const rooms = ref<Room[]>([])
const roomId = ref<number | null>(null)
const live = ref<LiveState | null>(null)
const pump = ref<PumpStatus | null>(null)
let timer = 0

const cells = computed<(LiveCamera | null)[]>(() => {
  const bySlot = new Map((live.value?.cameras ?? []).map((item) => [item.slot, item]))
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

onMounted(async () => {
  await loadRooms()
  await loadPump()
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
    <div class="monitor-grid">
      <StreamCell v-for="(camera, index) in cells" :key="index" :camera="camera" />
    </div>
  </div>
</template>
