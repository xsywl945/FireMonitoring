<template>
  <div class="app-shell">
    <aside class="app-sidebar" :class="{ open: mobileNavOpen }">
      <div class="brand-lockup">
        <div class="brand-mark"><span class="brand-flame" /></div>
        <div><strong>燧巡</strong><small>FIRE INTELLIGENCE</small></div>
      </div>

      <nav class="main-nav" aria-label="主导航">
        <RouterLink v-for="item in navigation" :key="item.path" :to="item.path" @click="mobileNavOpen = false">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
          <b v-if="item.badge">{{ item.badge }}</b>
        </RouterLink>
      </nav>

      <div class="sidebar-status">
        <div class="sidebar-status-head"><span>系统状态</span><strong><i /> 正常运行</strong></div>
        <div class="sidebar-stat-row"><span>摄像头</span><b>{{ onlineCameras }} / {{ totalCameras }} 在线</b></div>
        <div class="sidebar-stat-row"><span>推理模式</span><b>单摄时序</b></div>
        <div class="sidebar-stat-row"><span>本地时间</span><b>{{ clock }}</b></div>
      </div>
    </aside>
    <div v-if="mobileNavOpen" class="nav-backdrop" @click="mobileNavOpen = false" />

    <section class="app-main">
      <header class="topbar">
        <button class="mobile-menu" aria-label="打开导航" @click="mobileNavOpen = true">
          <span /><span /><span />
        </button>
        <div class="topbar-context">
          <span class="system-chip"><i /> 系统已布防</span>
          <span class="demo-chip">本地演示模式</span>
        </div>
        <div class="topbar-actions">
          <RouterLink class="alert-button" to="/incidents" aria-label="待确认预警">
            <el-icon><Bell /></el-icon><span v-if="newIncidentCount" class="alert-count">{{ newIncidentCount }}</span>
          </RouterLink>
          <el-dropdown trigger="click" @command="handleCommand">
            <button class="profile-button">
              <span class="avatar">{{ initials }}</span>
              <span class="profile-copy"><strong>{{ auth.user?.displayName || '管理员' }}</strong><small>系统管理员</small></span>
              <el-icon><ArrowDown /></el-icon>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="health">系统健康</el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>
      <main class="page-container"><RouterView /></main>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter, RouterLink, RouterView } from 'vue-router'
import { ArrowDown, Bell, DataAnalysis, Monitor, Operation, Setting, VideoCamera } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { cameraApi, incidentApi } from '@/api'

const router = useRouter()
const auth = useAuthStore()
const mobileNavOpen = ref(false)
const clock = ref('')
const onlineCameras = ref(0)
const totalCameras = ref(0)
const newIncidentCount = ref(0)
const navigation = computed(() => [
  { path: '/dashboard', label: '运行总览', icon: DataAnalysis },
  { path: '/monitor', label: '实时监控', icon: Monitor },
  { path: '/incidents', label: '预警事件', icon: Operation, badge: newIncidentCount.value ? String(newIncidentCount.value) : undefined },
  { path: '/devices', label: '区域与设备', icon: VideoCamera },
  { path: '/health', label: '系统健康', icon: Setting },
])

const initials = computed(() => auth.user?.displayName.slice(-2) || '管理员')
const updateClock = () => {
  clock.value = new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date())
}
updateClock()
const timer = window.setInterval(updateClock, 1000)
onBeforeUnmount(() => window.clearInterval(timer))
onMounted(async () => {
  const [cameras, incidents] = await Promise.all([cameraApi.list(), incidentApi.list({ status: 'NEW' })])
  totalCameras.value = cameras.length
  onlineCameras.value = cameras.filter((camera) => camera.status === 'ONLINE').length
  newIncidentCount.value = incidents.length
})

function handleCommand(command: string) {
  if (command === 'logout') {
    auth.logout()
    router.replace('/login')
  } else if (command === 'health') router.push('/health')
}
</script>
