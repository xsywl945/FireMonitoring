<template>
  <div>
    <PageHeader title="大模型研判">
      <template #actions><el-button :loading="loading" @click="load">刷新</el-button></template>
    </PageHeader>
    <div v-if="config" class="model-connection"><span>{{ config.dashscope_model }}</span><span>{{ config.dashscope_configured ? '已配置' : '未配置密钥' }}</span><details v-if="!config.dashscope_configured"><summary>接入设置</summary><p>在项目 .env 中填写 DASHSCOPE_API_KEY，然后重启推理服务。</p></details></div>
    <p v-if="configError" class="muted">模型服务未连接</p>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <section v-loading="loading" class="analysis-list">
      <article v-for="record in records" :key="record.incident.id" class="panel analysis-record">
        <header><div><h2>#{{ record.incident.id }} · {{ record.incident.zoneName }}</h2><span class="muted">{{ formatDate(record.incident.startedAt) }}</span></div><StatusBadge :status="record.incident.status" /></header>
        <AnalysisResult :analysis="record.semanticAnalysis" />
        <RouterLink class="text-link" :to="`/incidents/${record.incident.id}`">查看事件</RouterLink>
      </article>
      <el-empty v-if="!loading && !error && !records.length" description="暂无预警研判记录" />
    </section>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import AnalysisResult from '@/components/AnalysisResult.vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { isMockMode } from '@/api/client'
import { incidentApi, inferenceApi } from '@/api'
import type { IncidentAnalysis, InferenceConfig } from '@/types/domain'
const records = ref<IncidentAnalysis[]>([])
const config = ref<InferenceConfig>()
const configError = ref(false)
const loading = ref(false)
const error = ref('')
let timer: number | undefined
async function load() {
  if (loading.value) return
  loading.value = true
  try { records.value = await incidentApi.analyses(); error.value = '' }
  catch { error.value = '无法获取研判记录，请检查后端连接后刷新。' }
  finally { loading.value = false }
}
function formatDate(date: string) { return new Date(date).toLocaleString('zh-CN', { hour12: false }) }
onMounted(() => { if (!isMockMode) void inferenceApi.config().then((result) => { config.value = result }).catch(() => { configError.value = true }); void load(); timer = window.setInterval(load, 10000) })
onBeforeUnmount(() => window.clearInterval(timer))
</script>
