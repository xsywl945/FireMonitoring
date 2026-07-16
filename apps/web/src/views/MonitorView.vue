<template>
  <div class="monitor-page">
    <PageHeader eyebrow="LIVE OPERATIONS" title="实时监控" description="双视角视频预览与融合检测状态">
      <template #actions>
        <el-select v-model="selectedZone" class="zone-selector" :prefix-icon="Location">
          <el-option v-for="zone in zones" :key="zone.id" :label="zone.name" :value="zone.id" />
        </el-select>
        <el-button plain :icon="FullScreen">全屏监控</el-button>
      </template>
    </PageHeader>

    <div class="monitor-toolbar">
      <div class="monitor-mode"><span class="system-chip"><i /> 实时分析中</span><span>双摄软同步窗口 500 ms</span><span>最后同步偏差 <b>32 ms</b></span></div>
      <div class="model-runtime"><span>YOLO11s</span><span>FP16</span><span>640 px</span><span>平均 146 ms</span></div>
    </div>

    <section class="monitor-workspace">
      <div class="stream-grid" :class="{ single: visibleCameras.length === 1 }">
        <StreamPlayer v-for="camera in visibleCameras" :key="camera.id" :camera="camera" />
        <div v-if="!loading && visibleCameras.length < 2" class="add-view-card">
          <div class="add-view-icon"><el-icon><Plus /></el-icon></div>
          <strong>第二视角尚未接入</strong>
          <p>接入 USB 或网络摄像头后，可启用双视角决策融合。</p>
          <RouterLink to="/devices"><el-button plain>配置摄像头</el-button></RouterLink>
        </div>
      </div>

      <aside class="detection-panel">
        <header><div><span class="panel-kicker">FUSION ENGINE</span><h2>融合研判</h2></div><span class="engine-state"><i /> ACTIVE</span></header>
        <div class="risk-orb risk-critical"><div><strong>94</strong><span>融合风险分</span></div></div>
        <div class="evidence-stack">
          <div><span><b>VIEW_A</b> 火焰 · 烟雾</span><strong>0.92</strong><i><em style="width:92%" /></i></div>
          <div><span><b>VIEW_B</b> 火焰</span><strong>0.89</strong><i><em style="width:89%" /></i></div>
          <div class="fusion-row"><span><b>时序证据</b> 连续 4 / 5 帧</span><strong>通过</strong></div>
        </div>
        <div class="detection-message"><el-icon><WarningFilled /></el-icon><div><strong>火焰与烟雾风险已确认</strong><p>双视角证据一致，已生成预警事件并进入人工确认流程。</p></div></div>
        <RouterLink class="incident-link" to="/incidents/24071601">查看事件 #24071601 <el-icon><ArrowRight /></el-icon></RouterLink>
        <div class="legend-row"><span><i class="fire" /> 火焰框</span><span><i class="smoke" /> 烟雾框</span><span><i class="normal" /> 正常</span></div>
      </aside>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ArrowRight, FullScreen, Location, Plus, WarningFilled } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import StreamPlayer from '@/components/StreamPlayer.vue'
import { cameraApi, zoneApi } from '@/api'
import type { Camera, Zone } from '@/types/domain'

const loading = ref(true)
const zones = ref<Zone[]>([])
const cameras = ref<Camera[]>([])
const selectedZone = ref<number>()
const visibleCameras = computed(() => cameras.value.filter((camera) => !selectedZone.value || camera.zoneId === selectedZone.value).slice(0, 2))

onMounted(async () => {
  try {
    ;[zones.value, cameras.value] = await Promise.all([zoneApi.list(), cameraApi.list()])
    selectedZone.value = zones.value[0]?.id
  } finally { loading.value = false }
})
</script>
