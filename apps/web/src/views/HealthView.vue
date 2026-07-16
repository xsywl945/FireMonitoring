<template>
  <div class="health-page">
    <PageHeader eyebrow="SYSTEM OBSERVABILITY" title="系统健康" description="检查本地服务、媒体链路和云端依赖的运行状态">
      <template #actions><span class="refresh-time"><el-icon><Timer /></el-icon> 自动刷新 30s</span><el-button plain :icon="Refresh" :loading="loading" @click="load">立即检查</el-button></template>
    </PageHeader>

    <section class="health-hero panel">
      <div class="health-ring"><span><strong>{{ healthyRate }}</strong><small>%</small></span></div>
      <div><span class="system-chip"><i /> 核心链路可用</span><h2>系统运行稳定</h2><p>{{ healthyCount }} 个服务正常，{{ degradedCount }} 个服务处于降级状态。云端服务异常不会阻塞基础火灾预警。</p></div>
      <div class="health-runtime"><span>连续运行</span><strong>02:36:18</strong><small>演示机 · Windows 11</small></div>
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
        <div class="resource-row"><div><span>GPU 显存</span><strong>2.8 / 8.0 GB</strong></div><el-progress :percentage="35" :show-text="false" color="#ff7849" /></div>
        <div class="resource-row"><div><span>系统内存</span><strong>8.4 / 15.3 GB</strong></div><el-progress :percentage="55" :show-text="false" color="#47b6f4" /></div>
        <div class="resource-row"><div><span>数据盘空间</span><strong>28 / 191 GB</strong></div><el-progress :percentage="15" :show-text="false" color="#38cca1" /></div>
        <div class="hardware-meta"><span><b>GPU 温度</b> 54 °C</span><span><b>模型吞吐</b> 9.8 FPS</span><span><b>队列深度</b> 0</span></div>
      </article>
      <article class="panel degradation-panel">
        <header class="panel-header"><div><h2>降级保护</h2><p>外部依赖异常时的当前策略</p></div></header>
        <div class="degradation-row"><span><el-icon><VideoCamera /></el-icon></span><div><strong>第二视角离线</strong><p>自动切换单摄时序确认并提高阈值</p></div><b>已启用</b></div>
        <div class="degradation-row"><span><el-icon><Cloudy /></el-icon></span><div><strong>云端 API 超时</strong><p>保留基础预警，标记语义研判不可用</p></div><b>已启用</b></div>
        <div class="degradation-row"><span><el-icon><Message /></el-icon></span><div><strong>短信发送失败</strong><p>指数退避重试并保留真实回执状态</p></div><b>已启用</b></div>
      </article>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Cloudy, Connection, Cpu, DataBoard, Files, Message, Refresh, Timer, VideoCamera } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import { healthApi } from '@/api'
import type { ServiceHealth } from '@/types/domain'

const loading = ref(false)
const services = ref<ServiceHealth[]>([])
const healthyCount = computed(() => services.value.filter((item) => item.status === 'HEALTHY').length)
const degradedCount = computed(() => services.value.filter((item) => item.status === 'DEGRADED').length)
const healthyRate = computed(() => services.value.length ? Math.round((healthyCount.value / services.value.length) * 100) : 0)

async function load() { loading.value = true; try { services.value = await healthApi.services() } finally { loading.value = false } }
function healthLabel(status: ServiceHealth['status']) { return { HEALTHY: '健康', DEGRADED: '降级', OFFLINE: '离线', UNKNOWN: '未知' }[status] }
function serviceIcon(key: string) { return ({ api: DataBoard, inference: Cpu, media: VideoCamera, redis: Connection, storage: Files, cloud: Cloudy, sms: Message } as Record<string, typeof Cpu>)[key] || DataBoard }
function formatTime(date: string) { return new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date(date)) }
const timer = window.setInterval(load, 30_000)
onMounted(load)
onBeforeUnmount(() => window.clearInterval(timer))
</script>
