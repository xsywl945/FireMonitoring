<script setup lang="ts">
import { onMounted, ref } from "vue"
import { useRouter } from "vue-router"
import { api } from "../api/client"
import type { AlertSummary } from "../api/types"
import { alertLabels, formatTime } from "../labels"

const router = useRouter()
const alerts = ref<AlertSummary[]>([])

onMounted(async () => {
  alerts.value = await api<AlertSummary[]>("/alerts")
})

function open(row: AlertSummary) {
  router.push(`/alerts/${row.id}`)
}

function positionText(row: AlertSummary) {
  if (!row.position) return ""
  return row.position.status === "ESTIMATED" ? "已定位" : "无法定位"
}
</script>

<template>
  <div class="panel">
    <div class="toolbar"><strong>告警</strong></div>
    <el-table :data="alerts" border @row-click="open">
      <el-table-column label="时间" width="200">
        <template #default="{ row }">{{ formatTime(row.started_at) }}</template>
      </el-table-column>
      <el-table-column prop="room_name" label="教室" />
      <el-table-column label="类型" width="140">
        <template #default="{ row }">{{ alertLabels[row.alert_type] || row.alert_type }}</template>
      </el-table-column>
      <el-table-column label="定位" width="120">
        <template #default="{ row }">{{ positionText(row) }}</template>
      </el-table-column>
      <el-table-column label="分析" width="120">
        <template #default="{ row }">{{ row.analysis_status || "未分析" }}</template>
      </el-table-column>
      <el-table-column prop="level" label="等级" width="80" />
    </el-table>
  </div>
</template>
