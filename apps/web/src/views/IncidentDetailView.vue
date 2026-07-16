<template>
  <div v-loading="loading" class="incident-detail-page">
    <div class="detail-back"><RouterLink to="/incidents"><el-icon><ArrowLeft /></el-icon> 返回事件列表</RouterLink></div>
    <template v-if="incident">
      <header class="incident-hero" :class="`hero-${incident.severity.toLowerCase()}`">
        <div class="incident-hero-main">
          <div class="hero-labels"><SeverityBadge :severity="incident.severity" /><StatusBadge :status="incident.status" /><span>#{{ incident.id }}</span></div>
          <h1>{{ incident.zoneName }}</h1>
          <p><span><el-icon><Warning /></el-icon> {{ primaryTypeLabels[incident.primaryType] }}</span><span><el-icon><Clock /></el-icon> {{ formatDate(incident.startedAt) }}</span><span><el-icon><Location /></el-icon> 区域 {{ incident.zoneId }}</span></p>
        </div>
        <div class="hero-score"><strong>{{ Math.round((incident.fusionScore || 0) * 100) }}</strong><span>融合风险分</span></div>
        <div v-if="availableActions.length" class="incident-actions">
          <el-button v-for="action in availableActions" :key="action.action" :type="action.primary ? 'primary' : 'default'" @click="openAction(action.action)">{{ action.label }}</el-button>
        </div>
        <div v-else class="incident-closed"><el-icon><CircleCheck /></el-icon> 事件流程已结束</div>
      </header>

      <section class="detail-layout">
        <div class="detail-main-column">
          <article class="panel evidence-panel">
            <header class="panel-header"><div><h2>双视角证据</h2><p>事件确认时刻的关键帧与模型检测结果</p></div><span class="sync-chip">同步偏差 32 ms</span></header>
            <div v-if="incident.observations.length" class="evidence-grid">
              <div v-for="observation in incident.observations" :key="observation.id" class="evidence-card">
                <div class="evidence-frame">
                  <div class="evidence-mock-room"><span class="room-window" /><span class="room-board" /><span class="room-desk desk-a" /><span class="room-desk desk-b" /></div>
                  <div v-for="(detection, index) in observation.detections" :key="index" class="detection-box" :class="detection.className" :style="detectionStyle(detection.bboxXyxy)"><b>{{ detection.className === 'fire' ? '火焰' : '烟雾' }} {{ Math.round(detection.confidence * 100) }}%</b></div>
                  <span class="evidence-role">{{ observation.viewRole }}</span>
                  <span class="evidence-time">{{ formatTime(observation.capturedAt) }}</span>
                </div>
                <footer><div><strong>{{ observation.cameraName }}</strong><span>{{ observation.detections.length }} 个目标 · 时序分 {{ observation.temporalScore.toFixed(2) }}</span></div><el-button link type="primary">查看原图</el-button></footer>
              </div>
            </div>
            <el-empty v-else description="该事件暂无可显示的关键帧" />
            <div class="fusion-explanation"><span class="explanation-icon"><el-icon><Connection /></el-icon></span><div><strong>为什么触发本次预警？</strong><p>VIEW_A 与 VIEW_B 在 500 ms 融合窗口内给出一致的火焰证据，且单摄时序规则连续 4 / 5 帧通过。系统融合分 {{ (incident.fusionScore || 0).toFixed(2) }}，超过严重预警阈值 0.90。</p></div></div>
          </article>

          <article class="panel semantic-panel">
            <header class="panel-header"><div><h2>多模态语义研判</h2><p>云端模型基于双视角关键帧生成的辅助判断</p></div><span v-if="incident.semanticAnalysis?.model" class="model-chip">{{ incident.semanticAnalysis.model }}</span></header>
            <template v-if="incident.semanticAnalysis?.state === 'COMPLETED'">
              <div class="semantic-summary"><el-icon><MagicStick /></el-icon><p>{{ incident.semanticAnalysis.summary }}</p></div>
              <div class="semantic-grid">
                <div><span>疑似火源性质</span><p>{{ incident.semanticAnalysis.sourceNature || '未能确定' }}</p></div>
                <div><span>场景风险</span><p>{{ incident.semanticAnalysis.sceneRisk || '暂无补充' }}</p></div>
              </div>
              <div v-if="incident.semanticAnalysis.recommendations?.length" class="recommendation-list"><strong>建议操作</strong><ol><li v-for="item in incident.semanticAnalysis.recommendations" :key="item">{{ item }}</li></ol></div>
              <p v-if="incident.semanticAnalysis.uncertainty" class="uncertainty-note"><el-icon><InfoFilled /></el-icon><span><b>不确定性说明：</b>{{ incident.semanticAnalysis.uncertainty }}</span></p>
            </template>
            <div v-else-if="incident.semanticAnalysis?.state === 'PENDING'" class="analysis-pending"><div class="signal-loader"><span /><span /><span /></div><strong>云端语义研判进行中</strong><p>基础预警不受云端分析进度影响</p></div>
            <div v-else class="analysis-pending"><el-icon><Warning /></el-icon><strong>云端研判暂不可用</strong><p>本次预警仍由视觉检测与时序融合证据支撑</p></div>
            <footer class="ai-disclaimer">AI 研判仅作为辅助信息，不能替代现场人员和专业消防判断。</footer>
          </article>
        </div>

        <aside class="detail-side-column">
          <article class="panel timeline-panel">
            <header class="panel-header"><div><h2>处置时间线</h2><p>检测、通知与人工操作审计</p></div></header>
            <el-timeline>
              <el-timeline-item v-for="entry in incident.timeline" :key="entry.id" :timestamp="formatDate(entry.occurredAt)" placement="top" :type="entry.action.includes('解决') ? 'success' : entry.action.includes('误报') ? 'info' : 'warning'">
                <strong>{{ entry.action }}</strong><span>{{ entry.actor }}</span><p v-if="entry.note">{{ entry.note }}</p>
              </el-timeline-item>
            </el-timeline>
          </article>
          <article class="panel notification-panel">
            <header class="panel-header"><div><h2>通知状态</h2><p>事件触发后的外部通知链路</p></div></header>
            <div class="notification-row"><span class="notice-icon sms">短</span><div><strong>阿里云短信</strong><span>演示白名单 · 已送达</span></div><el-icon class="success-icon"><CircleCheckFilled /></el-icon></div>
            <div class="notification-row"><span class="notice-icon app">站</span><div><strong>站内预警</strong><span>1 名值班员已收到</span></div><el-icon class="success-icon"><CircleCheckFilled /></el-icon></div>
            <div class="notification-audit">最近更新 {{ formatTime(incident.startedAt) }} · 通知冷却窗口生效中</div>
          </article>
        </aside>
      </section>
    </template>
    <el-result v-else-if="!loading" icon="warning" title="事件不存在" sub-title="该事件可能已被删除或你没有查看权限"><template #extra><RouterLink to="/incidents"><el-button type="primary">返回事件列表</el-button></RouterLink></template></el-result>

    <el-dialog v-model="actionDialog" :title="actionTitle" width="min(500px, 92vw)">
      <el-form label-position="top">
        <el-form-item v-if="selectedAction === 'MARK_FALSE_ALARM'" label="误报原因" required><el-select v-model="actionForm.falseAlarmReason" style="width:100%" placeholder="请选择"><el-option label="水蒸气" value="STEAM" /><el-option label="灰尘" value="DUST" /><el-option label="强光" value="LIGHT" /><el-option label="屏幕内容" value="SCREEN_CONTENT" /><el-option label="其他" value="OTHER" /></el-select></el-form-item>
        <el-form-item label="处置说明"><el-input v-model="actionForm.note" type="textarea" :rows="4" maxlength="2000" show-word-limit placeholder="记录现场确认、处置措施或误报依据" /></el-form-item>
      </el-form>
      <div class="action-warning"><el-icon><InfoFilled /></el-icon>操作会记录到审计时间线中，提交后不可删除。</div>
      <template #footer><el-button @click="actionDialog = false">取消</el-button><el-button type="primary" :loading="submitting" @click="submitAction">确认提交</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowLeft, CircleCheck, CircleCheckFilled, Clock, Connection, InfoFilled, Location, MagicStick, Warning } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import SeverityBadge from '@/components/SeverityBadge.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { incidentApi } from '@/api'
import { primaryTypeLabels } from '@/config/labels'
import type { IncidentAction, IncidentDetail } from '@/types/domain'

const route = useRoute()
const loading = ref(true)
const submitting = ref(false)
const incident = ref<IncidentDetail>()
const actionDialog = ref(false)
const selectedAction = ref<IncidentAction>('ACKNOWLEDGE')
const actionForm = reactive<{ note: string; falseAlarmReason?: 'STEAM' | 'DUST' | 'LIGHT' | 'SCREEN_CONTENT' | 'OTHER' }>({ note: '' })
const actionTitle = computed(() => ({ ACKNOWLEDGE: '确认预警事件', START_HANDLING: '开始现场处置', RESOLVE: '解决并归档事件', MARK_FALSE_ALARM: '标记为误报' }[selectedAction.value]))
const availableActions = computed(() => {
  if (!incident.value) return []
  if (incident.value.status === 'NEW') return [{ action: 'ACKNOWLEDGE' as const, label: '确认事件', primary: true }, { action: 'MARK_FALSE_ALARM' as const, label: '标记误报' }]
  if (incident.value.status === 'ACKNOWLEDGED') return [{ action: 'START_HANDLING' as const, label: '开始处置', primary: true }, { action: 'MARK_FALSE_ALARM' as const, label: '标记误报' }]
  if (incident.value.status === 'HANDLING') return [{ action: 'RESOLVE' as const, label: '解决事件', primary: true }]
  return []
})

async function load() {
  loading.value = true
  try { incident.value = await incidentApi.get(Number(route.params.id)) } catch { incident.value = undefined } finally { loading.value = false }
}
function openAction(action: IncidentAction) { selectedAction.value = action; actionForm.note = ''; actionForm.falseAlarmReason = undefined; actionDialog.value = true }
async function submitAction() {
  if (selectedAction.value === 'MARK_FALSE_ALARM' && !actionForm.falseAlarmReason) { ElMessage.warning('请选择误报原因'); return }
  submitting.value = true
  try { incident.value = await incidentApi.transition(Number(route.params.id), { action: selectedAction.value, note: actionForm.note || undefined, falseAlarmReason: actionForm.falseAlarmReason }); actionDialog.value = false; ElMessage.success('事件状态已更新') } finally { submitting.value = false }
}
function formatDate(date: string) { return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date(date)) }
function formatTime(date: string) { return new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date(date)) }
function detectionStyle(box: [number, number, number, number]) { return { left: `${(box[0] / 640) * 100}%`, top: `${(box[1] / 480) * 100}%`, width: `${((box[2] - box[0]) / 640) * 100}%`, height: `${((box[3] - box[1]) / 480) * 100}%` } }
onMounted(load)
</script>
