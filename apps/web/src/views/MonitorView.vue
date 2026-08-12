<template>
  <div class="monitor-page">
    <PageHeader eyebrow="LIVE OPERATIONS" title="实时监控" description="本地单摄像头视频、YOLO 检测与时序预警状态">
      <template #actions>
        <el-select v-model="selectedZone" class="zone-selector" :prefix-icon="Location">
          <el-option v-for="zone in zones" :key="zone.id" :label="zone.name" :value="zone.id" />
        </el-select>
        <el-button plain :icon="FullScreen">全屏监控</el-button>
      </template>
    </PageHeader>

    <div class="monitor-toolbar">
      <div class="monitor-mode">
        <span class="system-chip"><i /> {{ runtime?.status === 'RUNNING' ? '实时分析中' : '推理服务未运行' }}</span>
        <span>单摄时序确认 <b>3 / 5 帧</b></span>
        <span>累计确认 <b>{{ runtime?.incidentsConfirmed || 0 }}</b> 起事件</span>
      </div>
      <div class="model-runtime">
        <span>{{ runtime?.modelVersion || 'YOLO11s' }}</span><span>CUDA FP16</span><span>640 px</span>
        <span>{{ live?.processTimeMs ? `${live.processTimeMs.toFixed(0)} ms/帧` : '等待首帧' }}</span>
      </div>
    </div>

    <section class="monitor-workspace">
      <div class="stream-grid single">
        <StreamPlayer v-for="camera in visibleCameras" :key="camera.id" :camera="camera" />
        <el-empty v-if="!loading && !visibleCameras.length" description="当前区域尚未绑定摄像头" />
      </div>

      <aside class="detection-panel">
        <header>
          <div><span class="panel-kicker">SINGLE CAMERA ENGINE</span><h2>实时检测</h2></div>
          <span class="engine-state"><i /> {{ live?.ready ? 'ACTIVE' : 'WAITING' }}</span>
        </header>
        <div class="risk-orb" :class="strongestConfidence ? 'risk-active' : 'risk-normal'" :style="riskOrbStyle">
          <div><strong>{{ Math.round(strongestConfidence * 100) }}</strong><span>当前最高置信度</span></div>
        </div>
        <div v-if="live?.detections.length" class="evidence-stack">
          <div v-for="(detection, index) in live.detections" :key="index">
            <span><b>SINGLE</b> {{ detection.className === 'fire' ? '火焰' : '烟雾' }}</span>
            <strong>{{ detection.confidence.toFixed(2) }}</strong>
            <i><em :style="{ width: `${detection.confidence * 100}%` }" /></i>
          </div>
          <div class="fusion-row"><span><b>时序证据</b> 由后台 3 / 5 帧规则确认</span><strong>监测中</strong></div>
        </div>
        <div v-else class="evidence-stack">
          <div class="fusion-row"><span><b>当前画面</b> 未发现火焰或烟雾候选</span><strong>正常</strong></div>
        </div>
        <div class="detection-message">
          <el-icon><WarningFilled /></el-icon>
          <div>
            <strong>{{ live?.detections.length ? '检测到单帧候选目标' : '系统正在持续监测' }}</strong>
            <p>{{ live?.detections.length ? '候选目标需通过单摄时序规则后才会生成预警，并触发云端语义研判。' : '网页显示的是本机 YOLO 标注画面；未达到时序阈值不会生成事件。' }}</p>
          </div>
        </div>
        <RouterLink v-if="latestIncident" class="incident-link" :to="`/incidents/${latestIncident.id}`">
          查看最近事件 #{{ latestIncident.id }} <el-icon><ArrowRight /></el-icon>
        </RouterLink>
        <div class="legend-row"><span><i class="fire" /> 火焰框</span><span><i class="smoke" /> 烟雾框</span><span><i class="normal" /> 正常</span></div>
      </aside>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ArrowRight, FullScreen, Location, WarningFilled } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import StreamPlayer from '@/components/StreamPlayer.vue'
import { cameraApi, incidentApi, inferenceApi, zoneApi } from '@/api'
import type { Camera, IncidentSummary, InferenceLiveStatus, InferenceRuntime, Zone } from '@/types/domain'

const loading = ref(true)
const zones = ref<Zone[]>([])
const cameras = ref<Camera[]>([])
const incidents = ref<IncidentSummary[]>([])
const runtime = ref<InferenceRuntime>()
const live = ref<InferenceLiveStatus>()
const selectedZone = ref<number>()
let pollTimer: number | undefined
let polling = false

const visibleCameras = computed(() => cameras.value
  .filter((camera) => !selectedZone.value || camera.zoneId === selectedZone.value)
  .slice(0, 1))
const strongestConfidence = computed(() => Math.max(0, ...(live.value?.detections.map((item) => item.confidence) || [])))
const riskOrbStyle = computed(() => {
  const percent = Math.round(strongestConfidence.value * 100)
  const color = strongestConfidence.value >= 0.7 ? '#ff5353' : strongestConfidence.value > 0 ? '#ff9f43' : '#38cca1'
  return { background: `conic-gradient(${color} 0 ${percent}%, #203c4c ${percent}% 100%)` }
})
const latestIncident = computed(() => incidents.value[0])

async function poll() {
  if (polling) return
  polling = true
  try {
    const [runtimeResult, liveResult, incidentResult] = await Promise.allSettled([
      inferenceApi.runtime(), inferenceApi.liveStatus(), incidentApi.list(),
    ])
    if (runtimeResult.status === 'fulfilled') runtime.value = runtimeResult.value
    if (liveResult.status === 'fulfilled') live.value = liveResult.value
    if (incidentResult.status === 'fulfilled') incidents.value = incidentResult.value
  } finally { polling = false }
}

onMounted(async () => {
  try {
    ;[zones.value, cameras.value] = await Promise.all([zoneApi.list(), cameraApi.list()])
    selectedZone.value = zones.value[0]?.id
    await poll()
    pollTimer = window.setInterval(poll, 1_500)
  } finally { loading.value = false }
})
onBeforeUnmount(() => { if (pollTimer) window.clearInterval(pollTimer) })
</script>
