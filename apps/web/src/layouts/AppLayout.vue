<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { useRoute, useRouter } from "vue-router"
import { ElNotification } from "element-plus"
import { clearSession, currentName, currentRole, currentToken } from "../api/client"
import DemoBadge from "../components/DemoBadge.vue"
import { loadDemoMode, type DemoMode } from "../demo"
import { alertLabels, roleLabels } from "../labels"

const route = useRoute()
const router = useRouter()
let socket: WebSocket | null = null
let closed = false

function beep() {
  const audio = new AudioContext()
  const oscillator = audio.createOscillator()
  const gain = audio.createGain()
  oscillator.frequency.value = 880
  oscillator.connect(gain)
  gain.connect(audio.destination)
  gain.gain.setValueAtTime(0.2, audio.currentTime)
  gain.gain.exponentialRampToValueAtTime(0.001, audio.currentTime + 0.4)
  oscillator.start()
  oscillator.stop(audio.currentTime + 0.4)
}

function connect() {
  const token = currentToken()
  if (closed || !token) return
  const protocol = location.protocol === "https:" ? "wss" : "ws"
  socket = new WebSocket(`${protocol}//${location.host}/api/v1/events?token=${encodeURIComponent(token)}`)
  socket.onmessage = (event) => {
    const payload = JSON.parse(event.data) as {
      kind: string
      alert_id: number
      room_name: string
      alert_type: string
    }
    window.dispatchEvent(new CustomEvent("fire-event", { detail: payload }))
    if (payload.kind !== "CONFIRMED") return
    const label = alertLabels[payload.alert_type] || payload.alert_type
    ElNotification({
      title: "火情告警",
      message: `${payload.room_name} ${label}`,
      type: "error",
      duration: 0,
      onClick: () => router.push(`/alerts/${payload.alert_id}`),
    })
    beep()
  }
  socket.onclose = (event) => {
    if (!closed && event.code !== 1008) window.setTimeout(connect, 1000)
  }
}

onMounted(async () => {
  connect()
  try {
    demo.value = await loadDemoMode()
  } catch {
    demo.value = null
  }
})
onBeforeUnmount(() => {
  closed = true
  socket?.close()
})

const role = currentRole()
const name = currentName()
const demo = ref<DemoMode | null>(null)

const items = computed(() => {
  const monitor = demo.value?.enabled ? "画面回放" : "实时监控"
  return [
    { path: "/rooms", label: "教室管理" },
    { path: "/cameras", label: "摄像头管理" },
    { path: "/monitor", label: monitor },
    ...(demo.value?.enabled
      ? [
          { path: "/dashboard", label: "数据大屏" },
          { path: "/twin", label: "数字孪生" },
        ]
      : []),
    { path: "/alerts", label: "告警研判" },
    { path: "/suppression", label: "灭火控制" },
    { path: "/users", label: "用户管理", admin: true },
    { path: "/config", label: "系统配置", admin: true },
  ]
})

const menu = computed(() => items.value.filter((item) => !item.admin || role === "admin"))
const showcase = computed(() => route.meta.showcase === true)
const active = computed(() => {
  if (route.path.startsWith("/rooms")) return "/rooms"
  if (route.path.startsWith("/alerts")) return "/alerts"
  return route.path
})
const crumbs = computed(() => {
  const parent = route.meta.parent as string | undefined
  const title = demo.value?.enabled && route.path === "/monitor" ? "画面回放" : (route.meta.title as string) || ""
  return parent ? [parent, title] : [title]
})

function logout() {
  clearSession()
  router.push("/login")
}
</script>

<template>
  <div v-if="showcase" class="showcase">
    <router-view />
  </div>
  <div v-else class="shell">
    <aside class="sider">
      <div class="brand">火情监控</div>
      <el-menu router :default-active="active">
        <el-menu-item v-for="item in menu" :key="item.path" :index="item.path">
          {{ item.label }}
        </el-menu-item>
      </el-menu>
    </aside>
    <div class="main">
      <header class="top">
        <el-breadcrumb>
          <el-breadcrumb-item v-for="item in crumbs" :key="item">{{ item }}</el-breadcrumb-item>
        </el-breadcrumb>
        <div class="user">
          <DemoBadge v-if="demo?.enabled" :synthetic="demo.synthetic" />
          <span>{{ name }}（{{ roleLabels[role || ""] || role }}）</span>
          <el-button link type="primary" @click="logout">退出</el-button>
        </div>
      </header>
      <section class="content">
        <router-view />
      </section>
    </div>
  </div>
</template>
