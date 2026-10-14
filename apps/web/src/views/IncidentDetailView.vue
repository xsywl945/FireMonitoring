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
        <div v-if="availableActions.length" class="incident-actions">
          <el-button v-for="action in availableActions" :key="action.action" :type="action.primary ? 'primary' : 'default'" @click="openAction(action.action)">{{ action.label }}</el-button>
        </div>
        <div v-else class="incident-closed"><el-icon><CircleCheck /></el-icon> 已结束</div>
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
            <header class="panel-header"><div><h2>处理记录</h2></div></header>
            <div class="handling-records">
              <div v-for="entry in handlingRecords" :key="entry.id" class="handling-entry"><time>{{ formatDate(entry.occurredAt) }}</time><div><strong>{{ entry.action }}</strong><span v-if="entry.actor"> · {{ entry.actor }}</span><p v-if="entry.note && !entry.note.startsWith('eventId=')">{{ entry.note }}</p></div></div>
              <p v-if="!handlingRecords.length" class="muted">暂无处理记录</p>
            </div>
          </article>

        </aside>
      </section>
    </template>
    <el-result v-else-if="!loading" icon="warning" title="事件不存在" sub-title="该事件可能已被删除或你没有查看权限"><template #extra><RouterLink to="/incidents"><el-button type="primary">返回事件列表</el-button></RouterLink></template></el-result>

    <el-dialog v-model="actionDialog" :title="actionTitle" width="min(500px, 92vw)">
      <el-form label-position="top">
        <el-form-item v-if="selectedAction === 'MARK_FALSE_ALARM'" label="误报原因" required><el-select v-model="actionForm.falseAlarmReason" style="width:100%" placeholder="请选择"><el-option label="水蒸气" value="STEAM" /><el-option label="灰尘" value="DUST" /><el-option label="强光" value="LIGHT" /><el-option label="屏幕内容" value="SCREEN_CONTENT" /><el-option label="其他" value="OTHER" /></el-select></el-form-item>
        <el-form-item label="处置说明"><el-input v-model="actionForm.note" type="textarea" :rows="4" maxlength="2000" show-word-limit placeholder="填写处理情况（选填）" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="actionDialog = false">取消</el-button><el-button type="primary" :loading="submitting" @click="submitAction">提交</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowLeft, CircleCheck, Clock, Location, Warning } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import AnalysisResult from '@/components/AnalysisResult.vue'
import SeverityBadge from '@/components/SeverityBadge.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { incidentApi } from '@/api'
import { primaryTypeLabels } from '@/config/labels'
import type { IncidentAction, IncidentDetail } from '@/types/domain'

const route = useRoute()
const loading = ref(true)
let pollTimer: number | undefined
let refreshing = false
const submitting = ref(false)
const incident = ref<IncidentDetail>()
const actionDialog = ref(false)
const selectedAction = ref<IncidentAction>('ACKNOWLEDGE')
const actionForm = reactive<{ note: string; falseAlarmReason?: 'STEAM' | 'DUST' | 'LIGHT' | 'SCREEN_CONTENT' | 'OTHER' }>({ note: '' })
const evidenceUrls = ref<Record<number, string>>({})
const actionTitle = computed(() => ({ ACKNOWLEDGE: '确认预警', START_HANDLING: '开始处置', RESOLVE: '解决事件', MARK_FALSE_ALARM: '标记误报' }[selectedAction.value]))
const handlingRecords = computed(() => (incident.value?.timeline || [])
  .filter((entry) => ['模型确认预警', '事件创建', '人工确认', '开始处置', '事件解决', '解决事件', '标记误报'].includes(entry.action))
  .map((entry) => ['模型确认预警', '事件创建'].includes(entry.action) ? { ...entry, action: '预警创建', actor: '', note: undefined } : entry)
  .sort((a, b) => Date.parse(a.occurredAt) - Date.parse(b.occurredAt)))
const availableActions = computed(() => {
  if (!incident.value) return []
  if (incident.value.status === 'NEW') return [{ action: 'ACKNOWLEDGE' as const, label: '确认事件', primary: true }, { action: 'MARK_FALSE_ALARM' as const, label: '标记误报' }]
  if (incident.value.status === 'ACKNOWLEDGED') return [{ action: 'START_HANDLING' as const, label: '开始处置', primary: true }, { action: 'MARK_FALSE_ALARM' as const, label: '标记误报' }]
  if (incident.value.status === 'HANDLING') return [{ action: 'RESOLVE' as const, label: '解决事件', primary: true }]
  return []
})

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
function openAction(action: IncidentAction) { selectedAction.value = action; actionForm.note = ''; actionForm.falseAlarmReason = undefined; actionDialog.value = true }
async function submitAction() {
  if (selectedAction.value === 'MARK_FALSE_ALARM' && !actionForm.falseAlarmReason) { ElMessage.warning('请选择误报原因'); return }
  submitting.value = true
  try { incident.value = await incidentApi.transition(Number(route.params.id), { action: selectedAction.value, note: actionForm.note || undefined, falseAlarmReason: actionForm.falseAlarmReason }); actionDialog.value = false; ElMessage.success('事件状态已更新') } catch { ElMessage.error('提交失败，请刷新后重试') } finally { submitting.value = false }
}
function formatDate(date: string) { return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date(date)) }
function formatTime(date: string) { return new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date(date)) }
function detectionStyle(box: [number, number, number, number], width: number, height: number) { return { left: `${(box[0] / width) * 100}%`, top: `${(box[1] / height) * 100}%`, width: `${((box[2] - box[0]) / width) * 100}%`, height: `${((box[3] - box[1]) / height) * 100}%` } }
function viewOriginal(index: number) { if (evidenceUrls.value[index]) window.open(evidenceUrls.value[index], '_blank', 'noopener,noreferrer') }
function cleanupEvidence() { Object.values(evidenceUrls.value).forEach(URL.revokeObjectURL); evidenceUrls.value = {} }
async function refresh() {
  if (refreshing || loading.value || submitting.value) return
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
