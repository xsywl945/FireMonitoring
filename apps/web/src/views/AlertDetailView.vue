<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { useRoute } from "vue-router"
import { ElMessage } from "element-plus"
import FloorPlan from "../components/FloorPlan.vue"
import { api, fetchBlob } from "../api/client"
import type { AlertDetail } from "../api/types"
import { alertLabels, formatTime, messageOf } from "../labels"

const route = useRoute()
const alertId = computed(() => Number(route.params.id))
const detail = ref<AlertDetail | null>(null)
const images = ref<Record<number, string>>({})
const note = ref("")

async function loadImages(alert: AlertDetail) {
  for (const url of Object.values(images.value)) URL.revokeObjectURL(url)
  const next: Record<number, string> = {}
  for (const frame of alert.frames) {
    next[frame.camera_id] = await fetchBlob(`/alerts/${alert.id}/frames/${frame.camera_id}`)
  }
  images.value = next
}

async function load() {
  const alert = await api<AlertDetail>(`/alerts/${alertId.value}`)
  detail.value = alert
  await loadImages(alert)
}

async function rerun() {
  try {
    await api(`/alerts/${alertId.value}/analysis`, { method: "POST" })
    await load()
  } catch (error) {
    ElMessage.error(messageOf(error))
  }
}

async function addNote() {
  if (!note.value.trim()) return
  try {
    await api(`/alerts/${alertId.value}/dispositions`, {
      method: "POST",
      body: JSON.stringify({ note: note.value.trim() }),
    })
    note.value = ""
    await load()
  } catch (error) {
    ElMessage.error(messageOf(error))
  }
}

function onFireEvent(event: Event) {
  const payload = (event as CustomEvent).detail as { alert_id: number; kind: string }
  if (payload.alert_id === alertId.value && payload.kind !== "CONFIRMED") load()
}

onMounted(() => {
  window.addEventListener("fire-event", onFireEvent)
  load()
})
onBeforeUnmount(() => {
  window.removeEventListener("fire-event", onFireEvent)
  for (const url of Object.values(images.value)) URL.revokeObjectURL(url)
})
</script>

<template>
  <div v-if="detail" class="stack">
    <div class="panel">
      <div>{{ detail.room_name }} / {{ alertLabels[detail.alert_type] || detail.alert_type }}</div>
      <div>{{ formatTime(detail.started_at) }}</div>
      <div v-if="detail.position?.status === 'ESTIMATED' && detail.position.xyz">
        已定位 {{ detail.position.xyz.map((item) => item.toFixed(2)).join(", ") }}
        ，条件数 {{ detail.position.condition_number }}
        ，支撑摄像头 {{ detail.position.support_camera_ids.join("、") }}
      </div>
      <div v-else>无法定位</div>
    </div>
    <div class="panel">
      <div class="toolbar"><strong>关键帧</strong></div>
      <div class="frames">
        <div v-for="frame in detail.frames" :key="frame.camera_id">
          <img :src="images[frame.camera_id]" :alt="frame.camera_name" />
          <div class="frame-meta">{{ frame.camera_name }}</div>
        </div>
      </div>
    </div>
    <div class="panel">
      <div class="toolbar">
        <strong>大模型分析</strong>
        <el-button @click="rerun">重新分析</el-button>
      </div>
      <template v-if="detail.analysis">
        <p>状态：{{ detail.analysis.status }}</p>
        <p v-if="detail.analysis.risk_level">风险：{{ detail.analysis.risk_level }}</p>
        <p v-if="detail.analysis.burning_objects.length">
          燃烧物：{{ detail.analysis.burning_objects.join("、") }}
        </p>
        <p v-if="detail.analysis.people_at_risk === true || detail.analysis.people_at_risk === false">
          人员：{{ detail.analysis.people_at_risk ? "有人" : "未见人员" }}
        </p>
        <p>{{ detail.analysis.reasoning_summary }}</p>
        <ul>
          <li v-for="item in detail.analysis.recommended_actions" :key="item">{{ item }}</li>
        </ul>
        <p v-if="detail.analysis.uncertainties.length">不确定：{{ detail.analysis.uncertainties.join("；") }}</p>
        <p v-if="detail.analysis.error_code">{{ detail.analysis.error_code }}</p>
      </template>
      <p v-else>未分析</p>
    </div>
    <div v-if="detail.floor_plan" class="panel">
      <div class="toolbar"><strong>平面图</strong></div>
      <FloorPlan :room-id="detail.room_id" :plan="detail.floor_plan" :position="detail.position" />
    </div>
    <div class="panel">
      <div class="toolbar"><strong>处置记录</strong></div>
      <el-table :data="detail.dispositions" border>
        <el-table-column label="时间" width="200">
          <template #default="{ row }">{{ formatTime(row.occurred_at) }}</template>
        </el-table-column>
        <el-table-column prop="actor" label="人员" width="120" />
        <el-table-column prop="note" label="记录" />
      </el-table>
      <div style="display: flex; gap: 8px; margin-top: 12px">
        <el-input v-model="note" placeholder="处置说明" />
        <el-button type="primary" @click="addNote">记录</el-button>
      </div>
    </div>
  </div>
</template>
