<template>
  <div class="analysis-result">
    <template v-if="analysis?.state === 'COMPLETED'">
      <p v-if="analysis.summary" class="analysis-summary">{{ analysis.summary }}</p>
      <dl class="analysis-facts">
        <div><dt>火源</dt><dd>{{ sourceLabels[analysis.sourceNature || ''] || analysis.sourceNature || '不明' }}</dd></div>
        <div><dt>风险</dt><dd>{{ severityLabels[analysis.sceneRisk as Severity] || analysis.sceneRisk || '未确定' }}</dd></div>
      </dl>
      <div v-if="analysis.recommendations?.length"><strong class="result-label">处理建议</strong><ol><li v-for="item in analysis.recommendations" :key="item">{{ item }}</li></ol></div>
      <details v-if="analysis.uncertainty || analysis.model" class="result-details"><summary>补充信息</summary><p v-if="analysis.uncertainty">{{ analysis.uncertainty }}</p><small v-if="analysis.model">{{ analysis.model }}</small></details>
    </template>
    <p v-else-if="analysis?.state === 'PENDING'" class="muted">分析中…</p>
    <p v-else class="muted">{{ analysis?.state === 'FAILED' ? errorLabels[analysis.errorCode || ''] || '分析失败' : '暂无分析结果' }}</p>
  </div>
</template>
<script setup lang="ts">
import { severityLabels } from '@/config/labels'
import type { SemanticAnalysis, Severity } from '@/types/domain'
defineProps<{ analysis: SemanticAnalysis | null }>()
const sourceLabels: Record<string, string> = { electrical: '电气', open_flame: '明火', chemical: '化学反应', cooking: '烹饪', unknown: '不明' }
const errorLabels: Record<string, string> = { VLM_NOT_CONFIGURED: '未配置模型密钥', VLM_TIMEOUT: '分析超时', VLM_INVALID_RESPONSE: '返回结果无效', VLM_HTTP_ERROR: '模型服务连接失败', VLM_INVALID_IMAGE_COUNT: '缺少分析图片' }
</script>
