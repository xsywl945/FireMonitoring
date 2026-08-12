<template>
  <div class="health-page">
    <PageHeader eyebrow="SYSTEM OBSERVABILITY" title="系统健康" description="检查本地服务、媒体链路和云端依赖的运行状态">
      <template #actions><span class="refresh-time"><el-icon><Timer /></el-icon> 自动刷新 30s</span><el-button plain :icon="Refresh" :loading="loading" @click="load">立即检查</el-button></template>
    </PageHeader>

    <section class="health-hero panel">
      <div class="health-ring"><span><strong>{{ healthyRate }}</strong><small>%</small></span></div>
      <div><span class="system-chip"><i /> 核心链路可用</span><h2>系统运行稳定</h2><p>{{ healthyCount }} 个服务正常，{{ degradedCount }} 个服务处于降级状态。云端服务异常不会阻塞基础火灾预警。</p></div>
      <div class="health-runtime"><span>推理状态</span><strong>{{ runtime?.status || 'UNKNOWN' }}</strong><small>Windows 11 · RTX 5060 Laptop</small></div>
    </section>

    <section class="service-health-grid">
      <article v-for="service in services" :key="service.key" class="service-card panel" :class="service.status.toLowerCase()">
        <header><div class="service-icon"><el-icon><component :is="serviceIcon(service.key)" /></el-icon></div><span class="service-status"><i /> {{ healthLabel(service.status) }}</span></header>
        <h3>{{ service.name }}</h3><p>{{ service.description }}</p>
        <footer><span>延迟</span><strong>{{ service.latencyMs ? `${service.latencyMs} ms` : '—' }}</strong><small>{{ formatTime(service.updatedAt) }} 检查</small></footer>
      </article>
    </section>

    <section class="health-bottom-grid">
      <article class="panel resource-panel">
        <header class="panel-header"><div><h2>本机资源</h2><p>RTX 5060 Laptop · 推理工作负载</p></div></header>
        <div class="resource-row"><div><span>模型版本</span><strong>{{ runtime?.modelVersion || '—' }}</strong></div></div>
        <div class="resource-row"><div><span>累计处理帧</span><strong>{{ runtime?.framesProcessed || 0 }}</strong></div></div>
        <div class="resource-row"><div><span>累计确认事件</span><strong>{{ runtime?.incidentsConfirmed || 0 }}</strong></div></div>
        <div class="hardware-meta"><span><b>输入分辨率</b> {{ live?.imageWidth || '—' }} × {{ live?.imageHeight || '—' }}</span><span><b>单帧耗时</b> {{ live?.processTimeMs?.toFixed(0) || '—' }} ms</span><span><b>当前候选</b> {{ live?.detections.length || 0 }}</span></div>
      </article>
      <article class="panel degradation-panel">
        <header class="panel-header"><div><h2>降级保护</h2><p>外部依赖异常时的当前策略</p></div></header>
        <div class="degradation-row"><span><el-icon><VideoCamera /></el-icon></span><div><strong>第二视角</strong><p>本阶段采用单摄时序确认，双摄融合暂不启动</p></div><b>未接入</b></div>
        <div class="degradation-row"><span><el-icon><Cloudy /></el-icon></span><div><strong>云端 API 超时</strong><p>保留基础预警，标记语义研判不可用</p></div><b>已启用</b></div>
        <div class="degradation-row"><span><el-icon><Message /></el-icon></span><div><strong>短信通知</strong><p>当前里程碑仅使用站内实时预警</p></div><b>未启用</b></div>
      </article>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Cloudy, Connection, Cpu, DataBoard, Files, Message, Refresh, Timer, VideoCamera } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import { healthApi, inferenceApi } from '@/api'
import type { InferenceLiveStatus, InferenceRuntime, ServiceHealth } from '@/types/domain'

const loading = ref(false)
const services = ref<ServiceHealth[]>([])
const runtime = ref<InferenceRuntime>()
const live = ref<InferenceLiveStatus>()
const healthyCount = computed(() => services.value.filter((item) => item.status === 'HEALTHY').length)
const degradedCount = computed(() => services.value.filter((item) => item.status === 'DEGRADED').length)
const healthyRate = computed(() => services.value.length ? Math.round((healthyCount.value / services.value.length) * 100) : 0)

async function load() {
  loading.value = true
  try {
    const [serviceResult, runtimeResult, liveResult] = await Promise.allSettled([healthApi.services(), inferenceApi.runtime(), inferenceApi.liveStatus()])
    if (serviceResult.status === 'fulfilled') services.value = serviceResult.value
    if (runtimeResult.status === 'fulfilled') runtime.value = runtimeResult.value
    if (liveResult.status === 'fulfilled') live.value = liveResult.value
  } finally { loading.value = false }
}
function healthLabel(status: ServiceHealth['status']) { return { HEALTHY: '健康', DEGRADED: '降级', OFFLINE: '离线', UNKNOWN: '未知' }[status] }
function serviceIcon(key: string) { return ({ api: DataBoard, inference: Cpu, media: VideoCamera, redis: Connection, storage: Files, cloud: Cloudy, sms: Message } as Record<string, typeof Cpu>)[key] || DataBoard }
function formatTime(date: string) { return new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date(date)) }
const timer = window.setInterval(load, 30_000)
onMounted(load)
onBeforeUnmount(() => window.clearInterval(timer))
</script>
