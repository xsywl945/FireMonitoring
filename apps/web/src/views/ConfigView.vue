<script setup lang="ts">
import { onMounted, ref } from "vue"
import { api } from "../api/client"

const config = ref<Record<string, unknown> | null>(null)
const titles: Record<string, string> = {
  server: "服务",
  database: "数据库",
  minio: "MinIO",
  mediamtx: "MediaMTX",
  llm: "大模型",
  sms: "短信",
  model: "模型",
  temporal: "时序",
  localization: "定位",
  pump: "水泵",
  auth: "登录",
  cameras: "摄像头默认值",
  timezone: "时区",
}

function entries(value: unknown) {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return Object.entries(value as Record<string, unknown>)
  }
  return []
}

function text(value: unknown) {
  if (value === null || value === undefined) return ""
  if (typeof value === "object") return JSON.stringify(value, null, 2)
  return String(value)
}

onMounted(async () => {
  config.value = await api<Record<string, unknown>>("/config")
})
</script>

<template>
  <div v-if="config" class="stack">
    <div v-for="(value, key) in config" :key="key" class="panel">
      <h2 style="margin: 0 0 12px; font-size: 16px">{{ titles[key] || key }}</h2>
      <el-descriptions v-if="entries(value).length" :column="1" border>
        <el-descriptions-item v-for="[name, item] in entries(value)" :key="name" :label="name">
          <pre v-if="typeof item === 'object' && item !== null" class="config-value">{{ text(item) }}</pre>
          <span v-else>{{ text(item) }}</span>
        </el-descriptions-item>
      </el-descriptions>
      <div v-else>{{ text(value) }}</div>
    </div>
  </div>
</template>
