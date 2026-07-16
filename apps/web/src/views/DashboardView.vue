<template>
  <div class="dashboard-page">
    <PageHeader eyebrow="COMMAND CENTER" title="运行总览" description="实时掌握摄像头、模型和预警处置状态">
      <template #actions>
        <span class="refresh-time"><el-icon><Refresh /></el-icon> 数据更新于 {{ lastUpdated }}</span>
        <el-button plain :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
      </template>
    </PageHeader>

    <section class="metric-grid" aria-label="核心指标">
      <article class="metric-card metric-camera">
        <div class="metric-icon"><el-icon><VideoCamera /></el-icon></div>
        <div class="metric-copy"><span>在线摄像头</span><strong>{{ summary.onlineCameras }}<small> / {{ summary.totalCameras }}</small></strong><p><i class="positive" /> 双视角链路正常</p></div>
        <div class="metric-progress"><span :style="{ width: `${cameraRate}%` }" /></div>
      </article>
      <article class="metric-card metric-alert">
        <div class="metric-icon"><el-icon><Warning /></el-icon></div>
        <div class="metric-copy"><span>待确认事件</span><strong>{{ summary.newIncidents }}</strong><p><i class="urgent" /> 需要操作员关注</p></div>
        <RouterLink to="/incidents?status=NEW">立即查看 <el-icon><ArrowRight /></el-icon></RouterLink>
      </article>
      <article class="metric-card metric-handling">
        <div class="metric-icon"><el-icon><Aim /></el-icon></div>
        <div class="metric-copy"><span>正在处置</span><strong>{{ summary.handlingIncidents }}</strong><p><i /> 平均响应 01:48</p></div>
      </article>
      <article class="metric-card metric-total">
        <div class="metric-icon"><el-icon><DataLine /></el-icon></div>
        <div class="metric-copy"><span>今日事件</span><strong>{{ summary.todayIncidents }}</strong><p><em>↓ 18%</em> 较昨日同期</p></div>
      </article>
    </section>

    <section class="dashboard-grid">
      <article class="panel trend-panel">
        <header class="panel-header">
          <div><h2>检测趋势</h2><p>最近 7 小时模型候选检测数量</p></div>
          <span class="model-chip">YOLO · 双视角</span>
        </header>
        <TrendChart :data="trend" />
      </article>

      <article class="panel active-incident-panel">
        <header class="panel-header">
          <div><h2>当前重点事件</h2><p>按风险等级与发生时间排序</p></div>
          <RouterLink to="/incidents">全部事件</RouterLink>
        </header>
        <div v-if="activeIncident" class="featured-incident">
          <div class="featured-top"><SeverityBadge :severity="activeIncident.severity" /><span>#{{ activeIncident.id }}</span></div>
          <h3>{{ activeIncident.zoneName }}</h3>
          <p><el-icon><Clock /></el-icon> {{ formatRelative(activeIncident.startedAt) }} · {{ primaryTypeLabels[activeIncident.primaryType] }}</p>
          <div class="fusion-meter"><span>双视角融合置信度</span><strong>94%</strong><div><i style="width:94%" /></div></div>
          <RouterLink class="incident-link" :to="`/incidents/${activeIncident.id}`">进入处置台 <el-icon><ArrowRight /></el-icon></RouterLink>
        </div>
        <el-empty v-else description="当前无活动事件" />
      </article>

      <article class="panel camera-overview-panel">
        <header class="panel-header">
          <div><h2>视频链路</h2><p>当前演示区域 · 求实楼 301</p></div>
          <RouterLink to="/monitor">打开监控</RouterLink>
        </header>
        <div class="mini-camera-grid">
          <div v-for="camera in cameras" :key="camera.id" class="mini-camera">
            <div class="mini-feed"><span class="mini-view">{{ camera.viewRole }}</span><i class="mini-scan" /><b><i /> LIVE</b></div>
            <div><strong>{{ camera.name }}</strong><span>{{ sourceLabels[camera.sourceType] }} · 720p</span></div>
          </div>
        </div>
      </article>

      <article class="panel health-summary-panel">
        <header class="panel-header"><div><h2>关键服务</h2><p>本机演示运行状态</p></div><RouterLink to="/health">详细状态</RouterLink></header>
        <div class="health-bars">
          <div v-for="service in services.slice(0, 4)" :key="service.key">
            <span><i :class="service.status.toLowerCase()" /> {{ service.name }}</span>
            <strong>{{ service.latencyMs ? `${service.latencyMs} ms` : '正常' }}</strong>
          </div>
        </div>
      </article>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ArrowRight, Aim, Clock, DataLine, Refresh, VideoCamera, Warning } from '@element-plus/icons-vue'
import { ElNotification } from 'element-plus'
import PageHeader from '@/components/PageHeader.vue'
import SeverityBadge from '@/components/SeverityBadge.vue'
import TrendChart from '@/components/TrendChart.vue'
import { cameraApi, dashboardApi, healthApi, incidentApi } from '@/api'
import { sourceLabels, primaryTypeLabels, severityOrder } from '@/config/labels'
import { createIncidentEventClient } from '@/events/incidentEventClient'
import type { Camera, DashboardSummary, IncidentSummary, ServiceHealth, TrendPoint } from '@/types/domain'

const loading = ref(false)
const summary = ref<DashboardSummary>({ onlineCameras: 0, totalCameras: 0, newIncidents: 0, handlingIncidents: 0, todayIncidents: 0 })
const incidents = ref<IncidentSummary[]>([])
const cameras = ref<Camera[]>([])
const trend = ref<TrendPoint[]>([])
const services = ref<ServiceHealth[]>([])
const lastUpdated = ref('--:--:--')
const cameraRate = computed(() => (summary.value.totalCameras ? (summary.value.onlineCameras / summary.value.totalCameras) * 100 : 0))
const activeIncident = computed(() => [...incidents.value].filter((item) => !['RESOLVED', 'FALSE_ALARM'].includes(item.status)).sort((a, b) => severityOrder[b.severity] - severityOrder[a.severity])[0])

async function load() {
  loading.value = true
  try {
    ;[summary.value, incidents.value, cameras.value, trend.value, services.value] = await Promise.all([
      dashboardApi.summary(), incidentApi.list(), cameraApi.list(), dashboardApi.trend(), healthApi.services(),
    ])
    lastUpdated.value = new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date())
  } finally { loading.value = false }
}

function formatRelative(date: string) {
  const minutes = Math.max(1, Math.floor((Date.now() - new Date(date).getTime()) / 60_000))
  return minutes < 60 ? `${minutes} 分钟前` : `${Math.floor(minutes / 60)} 小时前`
}

const eventClient = createIncidentEventClient()
eventClient.onIncident((incident) => {
  if (!incidents.value.some((item) => item.id === incident.id)) incidents.value.unshift(incident)
  ElNotification({ title: `${incident.zoneName} 检测到风险`, message: '新的火灾预警事件等待确认', type: 'warning', duration: 0 })
})
onMounted(() => { load(); eventClient.connect() })
onBeforeUnmount(() => eventClient.disconnect())
</script>
