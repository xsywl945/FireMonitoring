<template>
  <div class="incidents-page">
    <PageHeader eyebrow="INCIDENT MANAGEMENT" title="预警事件" description="集中确认、处置和复盘火灾风险事件">
      <template #actions><el-button plain :icon="Download">导出当前列表</el-button></template>
    </PageHeader>

    <section class="incident-filter panel">
      <div class="filter-tabs">
        <button v-for="item in filterStatuses" :key="item.value" :class="{ active: filters.status === item.value }" @click="filters.status = item.value">
          {{ item.label }} <b>{{ item.count }}</b>
        </button>
      </div>
      <div class="filter-controls">
        <el-select v-model="filters.severity" clearable placeholder="全部风险等级" style="width:160px"><el-option v-for="(label, value) in severityLabels" :key="value" :label="label" :value="value" /></el-select>
        <el-input v-model="search" clearable placeholder="搜索区域或事件编号" :prefix-icon="Search" style="width:230px" />
      </div>
    </section>

    <section class="panel incident-list-panel">
      <el-table v-loading="loading" :data="filteredIncidents" class="data-table incident-table" row-key="id" @row-click="openIncident">
        <el-table-column label="事件" min-width="165"><template #default="{ row }"><div class="incident-id-cell"><strong>#{{ row.id }}</strong><span>{{ formatDate(row.startedAt) }}</span></div></template></el-table-column>
        <el-table-column label="监控区域" min-width="220"><template #default="{ row }"><div class="zone-cell"><span class="zone-mini-icon"><el-icon><Location /></el-icon></span><div><strong>{{ row.zoneName }}</strong><span>区域 ID {{ row.zoneId }}</span></div></div></template></el-table-column>
        <el-table-column label="检测类型" width="150"><template #default="{ row }"><span class="type-chip">{{ primaryTypeLabels[row.primaryType as PrimaryType] }}</span></template></el-table-column>
        <el-table-column label="风险等级" width="130"><template #default="{ row }"><SeverityBadge :severity="row.severity" /></template></el-table-column>
        <el-table-column label="处置状态" width="130"><template #default="{ row }"><StatusBadge :status="row.status" /></template></el-table-column>
        <el-table-column label="响应耗时" width="120"><template #default="{ row }"><span :class="{ 'response-pending': !row.acknowledgedAt }">{{ responseTime(row) }}</span></template></el-table-column>
        <el-table-column width="70" fixed="right"><template #default><el-icon class="row-arrow"><ArrowRight /></el-icon></template></el-table-column>
      </el-table>
      <div v-if="!loading && !filteredIncidents.length" class="table-empty"><el-empty description="没有符合条件的事件" /></div>
      <footer class="table-footer"><span>共 {{ filteredIncidents.length }} 条记录</span><span>点击任一事件进入详细处置台</span></footer>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowRight, Download, Location, Search } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import SeverityBadge from '@/components/SeverityBadge.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { incidentApi } from '@/api'
import { primaryTypeLabels, severityLabels, statusLabels } from '@/config/labels'
import type { IncidentStatus, IncidentSummary, PrimaryType, Severity } from '@/types/domain'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const incidents = ref<IncidentSummary[]>([])
const search = ref('')
const filters = reactive<{ status?: IncidentStatus; severity?: Severity }>({ status: typeof route.query.status === 'string' ? route.query.status as IncidentStatus : undefined })
const filterStatuses = computed(() => [
  { label: '全部事件', value: undefined, count: incidents.value.length },
  ...(['NEW', 'ACKNOWLEDGED', 'HANDLING', 'RESOLVED', 'FALSE_ALARM'] as IncidentStatus[]).map((value) => ({ label: statusLabels[value], value, count: incidents.value.filter((item) => item.status === value).length })),
])
const filteredIncidents = computed(() => incidents.value.filter((item) => (!filters.status || item.status === filters.status) && (!filters.severity || item.severity === filters.severity) && (!search.value || item.zoneName.includes(search.value) || String(item.id).includes(search.value))))

async function load() { loading.value = true; try { incidents.value = await incidentApi.list() } finally { loading.value = false } }
function openIncident(row: IncidentSummary) { router.push(`/incidents/${row.id}`) }
function formatDate(date: string) { return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(date)) }
function responseTime(incident: IncidentSummary) {
  if (!incident.acknowledgedAt) return '等待响应'
  const seconds = Math.floor((new Date(incident.acknowledgedAt).getTime() - new Date(incident.startedAt).getTime()) / 1000)
  return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`
}
watch(() => filters.status, (status) => router.replace({ query: status ? { status } : {} }))
onMounted(load)
</script>
