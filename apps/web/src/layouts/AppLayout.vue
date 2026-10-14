<template>
  <div class="research-shell">
    <header class="research-header">
      <div><strong>火灾识别与预警系统</strong></div>
      <div class="session-info"><span>{{ isMockMode ? '模拟数据' : '本地服务' }}</span><span>{{ auth.user?.displayName }}</span><el-button size="small" @click="logout">退出登录</el-button></div>
    </header>
    <nav class="research-nav" aria-label="主导航">
      <RouterLink to="/monitor">火灾识别与预警</RouterLink>
      <RouterLink to="/analysis">大模型研判</RouterLink>
      <RouterLink to="/incidents">预警响应</RouterLink>
      <RouterLink class="settings-link" to="/rooms">教室与摄像头</RouterLink>
    </nav>
    <main class="page-container"><RouterView /></main>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import { ElNotification } from 'element-plus'
import { createIncidentEventClient } from '@/events/incidentEventClient'
import { RouterLink, RouterView, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { isMockMode } from '@/api/client'
const auth = useAuthStore()
const router = useRouter()
const events = createIncidentEventClient()
const notified = new Set<number>()
events.onIncident((incident) => {
  if (incident.status !== 'NEW' || notified.has(incident.id)) return
  notified.add(incident.id)
  ElNotification({ title: isMockMode ? '模拟预警' : '新预警', message: `${incident.zoneName} · 事件 #${incident.id}，点击查看证据`, type: 'warning', duration: 0, onClick: () => router.push(`/incidents/${incident.id}`) })
})
onMounted(() => events.connect())
onBeforeUnmount(() => { void events.disconnect() })
function logout() { auth.logout(); router.replace('/login') }
</script>
