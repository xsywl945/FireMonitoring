<script setup lang="ts">
import { onMounted, reactive, ref } from "vue"
import { useRouter } from "vue-router"
import { ElMessage } from "element-plus"
import { api, download } from "../api/client"
import type { AlertPage, Room } from "../api/types"
import { alertLabels, alertStatusLabels, formatTime, messageOf } from "../labels"

const router = useRouter()
const rooms = ref<Room[]>([])
const page = ref<AlertPage>({ items: [], total: 0, page: 1, page_size: 20 })
const current = ref(1)
const filters = reactive({
  roomId: undefined as number | undefined,
  from: undefined as Date | undefined,
  to: undefined as Date | undefined,
  level: "",
  fireClass: "",
  status: "",
})

function query() {
  const params = new URLSearchParams()
  if (filters.roomId) params.set("room_id", String(filters.roomId))
  if (filters.from) params.set("started_from", filters.from.toISOString())
  if (filters.to) params.set("started_to", filters.to.toISOString())
  if (filters.level) params.set("level", filters.level)
  if (filters.fireClass) params.set("fire_class", filters.fireClass)
  if (filters.status) params.set("status", filters.status)
  return params
}

async function load() {
  const params = query()
  params.set("page", String(current.value))
  params.set("page_size", "20")
  try {
    page.value = await api<AlertPage>(`/alerts?${params.toString()}`)
  } catch (error) {
    ElMessage.error(messageOf(error))
  }
}

function search() {
  current.value = 1
  load()
}

async function exportCsv() {
  try {
    await download(`/alerts/export?${query().toString()}`, "alerts.csv")
  } catch (error) {
    ElMessage.error(messageOf(error))
  }
}

function open(row: { id: number }) {
  router.push(`/alerts/${row.id}`)
}

onMounted(async () => {
  rooms.value = await api<Room[]>("/rooms")
  await load()
})
</script>

<template>
  <div class="panel">
    <div class="toolbar">
      <strong>告警</strong>
      <el-button @click="exportCsv">导出 CSV</el-button>
    </div>
    <div class="filters">
      <el-select v-model="filters.roomId" placeholder="教室" clearable style="width: 140px">
        <el-option v-for="room in rooms" :key="room.id" :label="room.name" :value="room.id" />
      </el-select>
      <el-date-picker v-model="filters.from" type="datetime" placeholder="开始时间" />
      <el-date-picker v-model="filters.to" type="datetime" placeholder="结束时间" />
      <el-select v-model="filters.level" placeholder="等级" clearable style="width: 100px">
        <el-option v-for="item in ['Ⅰ', 'Ⅱ', 'Ⅲ', 'Ⅳ']" :key="item" :label="item" :value="item" />
      </el-select>
      <el-select v-model="filters.fireClass" placeholder="类别" clearable style="width: 100px">
        <el-option v-for="item in ['A', 'B', 'C', 'D', 'E', 'F']" :key="item" :label="item" :value="item" />
      </el-select>
      <el-select v-model="filters.status" placeholder="处置状态" clearable style="width: 120px">
        <el-option v-for="(label, value) in alertStatusLabels" :key="value" :label="label" :value="value" />
      </el-select>
      <el-button type="primary" @click="search">查询</el-button>
    </div>
    <el-table :data="page.items" border @row-click="open">
      <el-table-column label="时间" width="200">
        <template #default="{ row }">{{ formatTime(row.started_at) }}</template>
      </el-table-column>
      <el-table-column prop="room_name" label="教室" />
      <el-table-column label="类型" width="140">
        <template #default="{ row }">{{ alertLabels[row.alert_type] || row.alert_type }}</template>
      </el-table-column>
      <el-table-column prop="level" label="等级" width="80" />
      <el-table-column prop="fire_classes" label="类别" width="100" />
      <el-table-column label="处置" width="100">
        <template #default="{ row }">{{ alertStatusLabels[row.status] || row.status }}</template>
      </el-table-column>
    </el-table>
    <div class="pager">
      <el-pagination
        v-model:current-page="current"
        :page-size="page.page_size"
        :total="page.total"
        layout="total, prev, pager, next"
        @current-change="load"
      />
    </div>
  </div>
</template>
