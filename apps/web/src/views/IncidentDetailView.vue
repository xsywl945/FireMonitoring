<template>
  <div v-loading="loading" class="incident-detail-page">
    <div class="detail-back"><RouterLink to="/incidents"><el-icon><ArrowLeft /></el-icon> 返回事件列表</RouterLink></div>
    <template v-if="incident">
      <header class="incident-hero" :class="`hero-${incident.severity.toLowerCase()}`">
        <div class="incident-hero-main">
          <div class="hero-labels"><SeverityBadge :severity="incident.severity" /><StatusBadge :status="incident.status" /><span>#{{ incident.id }}</span></div>
          <h1>{{ incident.zoneName }}</h1>
          <p><span><el-icon><Warning /></el-icon> {{ primaryTypeLabels[incident.primaryType] }}</span><span><el-icon><Clock /></el-icon> {{ formatDate(incident.startedAt) }}</span><span><el-icon><Location /></el-icon> 教室 {{ incident.zoneId }}</span></p>
        </div>
        <div class="hero-score"><strong>{{ incident.fusionScore != null ? incident.fusionScore.toFixed(2) : '未记录' }}</strong><span>时序证据分</span></div>
      </header>

      <section class="detail-layout">
        <div class="detail-main-column">
          <article class="panel evidence-panel">
            <header class="panel-header"><div><h2>现场图片</h2></div></header>
            <div v-if="incident.observations.length" class="evidence-grid">
              <div v-for="(observation, observationIndex) in incident.observations" :key="observation.id" class="evidence-card">
                <div class="evidence-frame">
                  <img v-if="evidenceUrls[observationIndex]" :src="evidenceUrls[observationIndex]" alt="事件关键帧" />
                  <div v-else class="stream-message">{{ observation.snapshotAvailable ? '图片加载失败' : '暂无图片' }}</div>
                  <div v-for="(detection, index) in (evidenceUrls[observationIndex] ? observation.detections : [])" :key="index" class="detection-box" :class="detection.className" :style="detectionStyle(detection.bboxXyxy, observation.imageWidth, observation.imageHeight)"><b>{{ detection.className === 'fire' ? '火焰' : '烟雾' }} {{ Math.round(detection.confidence * 100) }}%</b></div>

                  <span class="evidence-time">{{ formatTime(observation.capturedAt) }}</span>
                </div>
                <footer><div><strong>{{ observation.cameraName }}</strong><span>{{ observation.detections.length }} 个目标 · 时序分 {{ observation.temporalScore.toFixed(2) }}</span></div><el-button v-if="evidenceUrls[observationIndex]" link type="primary" @click="viewOriginal(observationIndex)">查看原图</el-button></footer>
              </div>
            </div>
            <el-empty v-else description="暂无图片" />

          </article>

          <article class="panel semantic-panel">
            <header class="panel-header"><h2>大模型研判</h2></header>
            <AnalysisResult :analysis="incident.semanticAnalysis" />
          </article>
        </div>

        <aside class="detail-side-column">
          <article class="panel timeline-panel">
            <header class="panel-header"><div><h2>事件记录</h2></div></header>
            <div class="handling-records">
              <div v-for="entry in handlingRecords" :key="entry.id" class="handling-entry"><time>{{ formatDate(entry.occurredAt) }}</time><div><strong>{{ entry.action }}</strong><span v-if="entry.actor"> · {{ entry.actor }}</span><p v-if="entry.note && !entry.note.startsWith('eventId=')">{{ entry.note }}</p></div></div>
              <p v-if="!handlingRecords.length" class="muted">暂无事件记录</p>
            </div>
          </article>

        </aside>
      </section>
    </template>
    <el-result v-else-if="!loading" icon="warning" title="事件不存在" sub-title="该事件可能已被删除或你没有查看权限"><template #extra><RouterLink to="/incidents"><el-button type="primary">返回事件列表</el-button></RouterLink></template></el-result>

  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowLeft, Clock, Location, Warning } from '@element-plus/icons-vue'
import AnalysisResult from '@/components/AnalysisResult.vue'
import SeverityBadge from '@/components/SeverityBadge.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { incidentApi } from '@/api'
import { primaryTypeLabels } from '@/config/labels'
import type { IncidentDetail } from '@/types/domain'

const route = useRoute()
const loading = ref(true)
let pollTimer: number | undefined
let refreshing = false
const incident = ref<IncidentDetail>()
const evidenceUrls = ref<Record<number, string>>({})
const handlingRecords = computed(() => (incident.value?.timeline || [])
  .slice().sort((a, b) => Date.parse(a.occurredAt) - Date.parse(b.occurredAt)))

async function load() {
  loading.value = true
  try {
    cleanupEvidence()
    incident.value = await incidentApi.get(Number(route.params.id))
    await Promise.all(incident.value.observations.map(async (observation, index) => {
      if (!observation.snapshotAvailable) return
      try { evidenceUrls.value[index] = URL.createObjectURL(await incidentApi.evidence(incident.value!.id, index)) } catch { /* evidence remains optional */ }
    }))
  } catch { incident.value = undefined } finally { loading.value = false }
}
function formatDate(date: string) { return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date(date)) }
function formatTime(date: string) { return new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date(date)) }
function detectionStyle(box: [number, number, number, number], width: number, height: number) { return { left: `${(box[0] / width) * 100}%`, top: `${(box[1] / height) * 100}%`, width: `${((box[2] - box[0]) / width) * 100}%`, height: `${((box[3] - box[1]) / height) * 100}%` } }
function viewOriginal(index: number) { if (evidenceUrls.value[index]) window.open(evidenceUrls.value[index], '_blank', 'noopener,noreferrer') }
function cleanupEvidence() { Object.values(evidenceUrls.value).forEach(URL.revokeObjectURL); evidenceUrls.value = {} }
async function refresh() {
  if (refreshing || loading.value) return
  refreshing = true
  try {
    const latest = await incidentApi.get(Number(route.params.id))
    const evidenceChanged = JSON.stringify(latest.observations) !== JSON.stringify(incident.value?.observations)
    incident.value = latest
    if (evidenceChanged) await load()
  } catch { /* Preserve loaded evidence during a temporary service interruption. */ }
  finally { refreshing = false }
}
watch(() => route.params.id, load)
onMounted(() => { void load(); pollTimer = window.setInterval(refresh, 5000) })
onBeforeUnmount(() => { window.clearInterval(pollTimer); cleanupEvidence() })
</script>
