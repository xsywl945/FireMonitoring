<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue"
import { api } from "../api/client"
import DemoBadge from "../components/DemoBadge.vue"
import TwinScene from "../components/TwinScene.vue"
import type { DemoStatus } from "../demo"

const status = ref<DemoStatus | null>(null)
let timer = 0

async function load() {
  status.value = await api<DemoStatus>("/demo")
}

onMounted(() => {
  timer = window.setInterval(() => void load(), 250)
  void load()
})

onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <div class="twin-page">
    <TwinScene :scene="status?.scene ?? null" />
    <aside>
      <DemoBadge :synthetic="status?.synthetic" />
      <h1>教室数字孪生</h1>
      <p class="muted">回放驱动，不是实况。</p>
      <dl>
        <div><dt>阶段</dt><dd>{{ status?.phase || "监视" }}</dd></div>
        <div><dt>火点</dt><dd>{{ status?.position?.xyz ? status.position.xyz.map((item) => item.toFixed(2)).join("，") : "尚未定位" }}</dd></div>
        <div><dt>云台</dt><dd>{{ (status?.actuator.pan_deg ?? 0).toFixed(1) }}° / {{ (status?.actuator.tilt_deg ?? 0).toFixed(1) }}°</dd></div>
        <div><dt>激光</dt><dd>{{ status?.actuator.laser === "ON" ? "开" : "关" }}</dd></div>
        <div><dt>水泵</dt><dd>{{ status && !status.pump_run ? "已禁用" : status?.actuator.pump === "ON" ? "运行" : "停止" }}</dd></div>
      </dl>
      <p v-if="status?.analysis?.level">等级 {{ status.analysis.level.grade }}</p>
      <p v-if="status?.message">{{ status.message }}</p>
    </aside>
  </div>
</template>
