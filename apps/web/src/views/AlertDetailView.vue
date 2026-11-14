<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { useRoute } from "vue-router"
import { ElMessage } from "element-plus"
import FloorPlan from "../components/FloorPlan.vue"
import type { PlanShape } from "../components/FloorPlan.vue"
import { api, fetchBlob } from "../api/client"
import type { AlertDetail } from "../api/types"
import {
  alertLabels,
  causeLabels,
  formatTime,
  growthLabels,
  messageOf,
  smokeColorLabels,
  smokeDensityLabels,
} from "../labels"

const route = useRoute()
const alertId = computed(() => Number(route.params.id))
const detail = ref<AlertDetail | null>(null)
const images = ref<Record<number, string>>({})
const note = ref("")

const analysis = computed(() => detail.value?.analysis ?? null)

const shapes = computed<PlanShape[]>(() => {
  const plan = detail.value?.floor_plan
  const spread = analysis.value?.spread
  const regions = (plan?.combustibles ?? []).map((item) => ({
    points: item.polygon,
    stroke: "#1e3a5f",
    fill: "rgba(30, 58, 95, 0.12)",
  }))
  if (!spread || spread.status !== "ESTIMATED") return regions
  return [
    ...regions,
    { points: spread.horizon_60s ?? [], stroke: "#98a2b3", fill: "rgba(152, 162, 179, 0.2)" },
    { points: spread.horizon_30s ?? [], stroke: "#b54708", fill: "rgba(181, 71, 8, 0.18)" },
    { points: spread.now ?? [], stroke: "#9f2d20", fill: "rgba(159, 45, 32, 0.35)" },
  ]
})

const chart = computed(() => {
  const growth = analysis.value?.growth
  const rows = growth?.curve?.length
    ? growth.curve.map((item) => ({ t: item.t, y: item.q }))
    : (growth?.samples ?? []).map((item) => ({ t: item.t, y: item.q ?? item.area ?? 0 }))
  if (rows.length < 2) return ""
  const maxT = Math.max(...rows.map((item) => item.t))
  const maxY = Math.max(...rows.map((item) => item.y))
  if (maxT <= 0 || maxY <= 0) return ""
  return rows
    .map((item) => `${(item.t / maxT) * 300 + 8},${152 - (item.y / maxY) * 136}`)
    .join(" ")
})

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

function seconds(value: number | undefined) {
  if (value === undefined) return ""
  return value <= 0 ? "已达到" : `${value.toFixed(0)} 秒`
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
      <div v-if="analysis">等级 {{ analysis.level.grade }}</div>
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
        <strong>火情研判</strong>
        <el-button @click="rerun">重新研判</el-button>
      </div>
      <template v-if="analysis">
        <el-alert
          v-if="analysis.scene.mismatch"
          type="warning"
          :closable="false"
          :title="`配置场景是${analysis.scene.configured_label}，模型观察到${analysis.scene.observed_label}`"
          style="margin-bottom: 12px"
        />
        <p>状态：{{ analysis.status }}　等级：{{ analysis.level.grade }}</p>
        <ul>
          <li v-for="reason in analysis.level.reasons" :key="reason">{{ reason }}</li>
        </ul>
        <el-table v-if="analysis.evidence" :data="analysis.evidence.burning_objects" border>
          <el-table-column prop="frame_index" label="画面" width="80" />
          <el-table-column prop="name" label="燃烧物" width="160" />
          <el-table-column prop="evidence" label="依据" />
        </el-table>
        <p v-if="analysis.evidence">
          疑似原因：{{ causeLabels[analysis.evidence.suspected_cause] || analysis.evidence.suspected_cause }}
          ；人员 {{ analysis.evidence.person_count }} 人
          <span v-if="analysis.evidence.person_location">，{{ analysis.evidence.person_location }}</span>
          ；烟 {{ smokeColorLabels[analysis.evidence.smoke_color] || analysis.evidence.smoke_color }}
          / {{ smokeDensityLabels[analysis.evidence.smoke_density] || analysis.evidence.smoke_density }}
        </p>
        <p v-if="analysis.evidence?.uncertainties.length">
          不确定：{{ analysis.evidence.uncertainties.join("；") }}
        </p>
        <p>
          火灾类别：{{ analysis.rules.details.map((item) => `${item.id} ${item.name}`).join("、") || "未定" }}
        </p>
        <p>建议灭火剂：{{ analysis.rules.recommended.join("、") || "无" }}</p>
        <p>禁止：{{ analysis.rules.forbidden.join("、") || "无" }}</p>
        <p v-if="analysis.rules.actions.length">处置顺序：{{ analysis.rules.actions.join("、") }}</p>
        <ul>
          <li v-for="item in analysis.rules.basis" :key="item">{{ item }}</li>
        </ul>
        <p v-if="analysis.size">
          估计火焰高度 {{ analysis.size.height_m.toFixed(2) }} m，底部直径
          {{ analysis.size.diameter_m.toFixed(2) }} m，热释放速率 {{ analysis.size.q_kw.toFixed(1) }} kW（估计值）
        </p>
        <p>{{ analysis.growth.reason }}</p>
        <p v-if="analysis.growth.bin">
          增长档位：{{ growthLabels[analysis.growth.bin] || analysis.growth.bin }}
          ；到 100 kW {{ seconds(analysis.growth.seconds_to_100kw) }}
          ；到 500 kW {{ seconds(analysis.growth.seconds_to_500kw) }}
        </p>
        <p v-if="analysis.growth.doubling_time_s !== undefined">
          框面积增长率 {{ analysis.growth.area_rate_px2_per_s?.toFixed(1) }} px²/s，倍增时间
          {{ analysis.growth.doubling_time_s.toFixed(1) }} 秒
        </p>
        <svg v-if="chart" class="chart" viewBox="0 0 320 160">
          <polyline :points="chart" fill="none" stroke="#9f2d20" stroke-width="1.5" />
        </svg>
        <p v-if="analysis.spread.status === 'ESTIMATED'">
          蔓延速度 {{ analysis.spread.speed_m_s?.toFixed(2) }} m/s，方向
          {{ analysis.spread.direction_deg?.toFixed(0) }}°
        </p>
        <pre class="oled">{{ analysis.texts.oled }}</pre>
        <p v-if="analysis.error_code">{{ analysis.error_code }}</p>
      </template>
      <p v-else>未研判</p>
    </div>
    <div v-if="detail.floor_plan" class="panel">
      <div class="toolbar"><strong>平面图</strong></div>
      <FloorPlan :room-id="detail.room_id" :plan="detail.floor_plan" :position="detail.position" :shapes="shapes" />
      <p>红线为当前范围，橙线为 30 秒外推，灰线为 60 秒外推，蓝线为可燃物区域。</p>
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
