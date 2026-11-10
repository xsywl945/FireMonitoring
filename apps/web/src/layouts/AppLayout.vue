<script setup lang="ts">
import { computed } from "vue"
import { useRoute, useRouter } from "vue-router"
import { clearSession, currentName, currentRole } from "../api/client"
import { roleLabels } from "../labels"

const route = useRoute()
const router = useRouter()
const role = currentRole()
const name = currentName()

const items = [
  { path: "/rooms", label: "教室管理" },
  { path: "/cameras", label: "摄像头管理" },
  { path: "/monitor", label: "实时监控" },
  { path: "/alerts", label: "告警研判" },
  { path: "/config", label: "系统配置", admin: true },
]

const menu = computed(() => items.filter((item) => !item.admin || role === "admin"))
const active = computed(() => {
  if (route.path.startsWith("/rooms")) return "/rooms"
  if (route.path.startsWith("/alerts")) return "/alerts"
  return route.path
})
const crumbs = computed(() => {
  const parent = route.meta.parent as string | undefined
  const title = (route.meta.title as string) || ""
  return parent ? [parent, title] : [title]
})

function logout() {
  clearSession()
  router.push("/login")
}
</script>

<template>
  <div class="shell">
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
