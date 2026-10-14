<template>
  <div class="monitor-page">
    <PageHeader title="火灾监控">
      <template #actions>
        <el-select v-model="selectedZone" class="zone-selector" placeholder="选择教室"><el-option v-for="zone in zones" :key="zone.id" :label="zone.name" :value="zone.id" /></el-select>
        <el-select v-model="selectedCameraId" class="camera-selector" placeholder="选择摄像头"><el-option v-for="camera in zoneCameras" :key="camera.id" :label="camera.name" :value="camera.id" /></el-select>
      </template>
    </PageHeader>
    <el-alert v-if="error || connectionError" :title="error || connectionError" type="error" :closable="false" />
    <section v-loading="loading" class="monitor-workspace">
      <div class="stream-grid single"><StreamPlayer v-if="selectedCamera" :key="selectedCamera.id" :camera="selectedCamera" :use-inference="usesLiveInference" /><div v-else class="panel empty-camera"><p>还没有摄像头</p><RouterLink class="text-link" to="/rooms">添加或绑定摄像头</RouterLink></div></div>
      <aside class="panel detection-panel">
        <h2>识别状态</h2>
        <dl class="runtime-facts">
          <div><dt>推理服务</dt><dd>{{ usesLiveInference && runtime ? runtime.status === 'RUNNING' ? '运行中' : runtime.status === 'STARTING' ? '启动中' : runtime.status === 'FAILED' ? '运行失败' : runtime.status === 'STOPPED' ? '已停止' : '待启动' : '未运行' }}</dd></div>
          <div><dt>模型版本</dt><dd>{{ usesLiveInference ? runtime?.modelVersion || '—' : '—' }}</dd></div>
          <div><dt>单帧耗时</dt><dd>{{ usesLiveInference && live?.processTimeMs != null ? `${live.processTimeMs.toFixed(0)} ms` : '—' }}</dd></div>
          <div><dt>最高置信度</dt><dd>{{ usesLiveInference && live?.ready ? `${Math.round(strongestConfidence * 100)}%` : '—' }}</dd></div>
          <div><dt>本次预警</dt><dd>{{ usesLiveInference ? runtime?.incidentsConfirmed ?? '—' : '—' }}</dd></div>
        </dl>
        <h3>当前检测目标</h3>
        <el-table v-if="usesLiveInference && live?.detections.length" :data="live.detections"><el-table-column label="类别"><template #default="{ row }">{{ row.className === 'fire' ? '火焰' : '烟雾' }}</template></el-table-column><el-table-column label="置信度"><template #default="{ row }">{{ row.confidence.toFixed(2) }}</template></el-table-column></el-table>
        <p v-else class="muted">{{ usesLiveInference && live?.ready && runtime?.status === 'RUNNING' ? '未检测到火焰或烟雾' : '暂无识别数据' }}</p>
        <p v-if="usesLiveInference && runtime?.lastError" class="error-note">{{ runtime.lastError }}</p>
        <RouterLink v-if="latestIncident" class="text-link" :to="`/incidents/${latestIncident.id}`">最近预警 #{{ latestIncident.id }}</RouterLink>
      </aside>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import PageHeader from '@/components/PageHeader.vue'
import StreamPlayer from '@/components/StreamPlayer.vue'
import { isMockMode } from '@/api/client'
import { cameraApi, incidentApi, inferenceApi, zoneApi } from '@/api'
import type { Camera, IncidentSummary, InferenceLiveStatus, InferenceRuntime, Zone } from '@/types/domain'

const loading = ref(true)
const error = ref('')
const connectionError = ref('')
const zones = ref<Zone[]>([])
const cameras = ref<Camera[]>([])
const incidents = ref<IncidentSummary[]>([])
const runtime = ref<InferenceRuntime>()
const live = ref<InferenceLiveStatus>()
const selectedZone = ref<number>()
const selectedCameraId = ref<number>()
let pollTimer: number | undefined
let polling = false

const zoneCameras = computed(() => cameras.value.filter((camera) => camera.zoneId === selectedZone.value))
const selectedCamera = computed(() => zoneCameras.value.find((camera) => camera.id === selectedCameraId.value))
const usesLiveInference = computed(() => Boolean(selectedCamera.value && (runtime.value?.status === 'RUNNING' || runtime.value?.status === 'STARTING') && runtime.value?.cameraId === selectedCamera.value.id && runtime.value?.zoneId === selectedZone.value))
watch(zoneCameras, (items) => {
  if (!items.some((camera) => camera.id === selectedCameraId.value)) selectedCameraId.value = items[0]?.id
})
const strongestConfidence = computed(() => Math.max(0, ...(live.value?.detections.map((item) => item.confidence) || [])))
const latestIncident = computed(() => incidents.value.find((item) => item.zoneId === selectedZone.value))

async function poll() {
  if (polling) return
  polling = true
  try {
    if (isMockMode) { incidents.value = await incidentApi.list(); return }
    const [runtimeResult, liveResult, incidentResult] = await Promise.allSettled([
      inferenceApi.runtime(), inferenceApi.liveStatus(), incidentApi.list(),
    ])
    runtime.value = runtimeResult.status === 'fulfilled' ? runtimeResult.value : undefined
    live.value = liveResult.status === 'fulfilled' ? liveResult.value : undefined
    connectionError.value = runtimeResult.status === 'rejected' || liveResult.status === 'rejected' ? '识别服务未连接' : incidentResult.status === 'rejected' ? '预警列表更新失败' : ''
    if (incidentResult.status === 'fulfilled') incidents.value = incidentResult.value
  } finally { polling = false }
}

onMounted(async () => {
  try {
    ;[zones.value, cameras.value] = await Promise.all([zoneApi.list(), cameraApi.list()])
    selectedZone.value = zones.value[0]?.id
    await poll()
    pollTimer = window.setInterval(poll, 1_500)
  } catch { error.value = '摄像头配置加载失败' } finally { loading.value = false }
})
onBeforeUnmount(() => { if (pollTimer) window.clearInterval(pollTimer) })
</script>
