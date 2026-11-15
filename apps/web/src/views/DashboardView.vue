<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { ElMessage } from "element-plus"
import { api, currentRole, fetchAuthorized } from "../api/client"
import DemoBadge from "../components/DemoBadge.vue"
import ReplayPane from "../components/ReplayPane.vue"
import TwinScene from "../components/TwinScene.vue"
import type { DemoStatus } from "../demo"
import { causeLabels, growthLabels, messageOf } from "../labels"

const status = ref<DemoStatus | null>(null)
const urls = ref<Record<number, string>>({})
const stage = ref<HTMLElement | null>(null)
const plan = ref<HTMLCanvasElement | null>(null)
const chart = ref<HTMLCanvasElement | null>(null)
const admin = currentRole() === "admin"
let timer = 0
let busy = false

const eventName: Record<string, string> = {
  CONFIRMED: "告警",
  LOCALIZED: "定位",
  ANALYSIS: "研判",
  SUP_SUSPECTED: "疑似",
  SUP_CONFIRMED: "确认",
  SUP_AIM: "瞄准",
  SUP_PENDING: "待喷",
  SUP_SPRAY: "喷射",
  SUP_REVIEW: "复核",
  SUP_OUT: "扑灭",
  SUP_BLOCK: "受阻",
  SUP_MANUAL: "人工",
}

const shownEvents = computed(() => (status.value?.events ?? []).filter((item) => eventName[item.kind]))
const cameras = computed(() => {
  const bySlot = new Map((status.value?.cameras ?? []).map((item) => [item.slot, item]))
  return [1, 2, 3, 4].map((slot) => bySlot.get(slot) ?? null)
})
const clock = computed(() => {
  const seconds = Math.max(0, status.value?.elapsed_s ?? 0)
  const whole = Math.floor(seconds)
  return `${String(Math.floor(whole / 60)).padStart(2, "0")}:${String(whole % 60).padStart(2, "0")}`
})

function fit() {
  const node = stage.value
  if (!node) return
  const scale = Math.min(window.innerWidth / 1920, window.innerHeight / 1080)
  node.style.transform = `scale(${scale})`
}

async function refreshFrames() {
  const current = status.value
  if (!current) return
  const nextUrls = { ...urls.value }
  for (const camera of current.cameras) {
    try {
      const blob = await fetchAuthorized(`/demo/frames/${camera.id}`)
      const next = URL.createObjectURL(blob)
      const previous = nextUrls[camera.id]
      nextUrls[camera.id] = next
      if (previous) URL.revokeObjectURL(previous)
    } catch {
      // 这一路还没有画面时保持上一帧。
    }
  }
  urls.value = nextUrls
}

function drawPlan() {
  const canvas = plan.value
  const scene = status.value?.scene
  if (!canvas || !scene) return
  const width = canvas.clientWidth
  const height = canvas.clientHeight
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext("2d")
  if (!ctx) return
  ctx.clearRect(0, 0, width, height)
  const pad = 28
  const scale = Math.min((width - pad * 2) / scene.width_m, (height - pad * 2) / scene.depth_m)
  const ox = (width - scene.width_m * scale) / 2
  const oy = (height + scene.depth_m * scale) / 2
  const point = (x: number, y: number) => [ox + x * scale, oy - y * scale]
  ctx.strokeStyle = "#8b9aab"
  ctx.strokeRect(ox, oy - scene.depth_m * scale, scene.width_m * scale, scene.depth_m * scale)
  ctx.fillStyle = "rgba(141,107,69,0.35)"
  for (const item of scene.furniture) {
    if (item.kind === "board") continue
    const [x1, y1] = point(item.min[0], item.min[1])
    const [x2, y2] = point(item.max[0], item.max[1])
    ctx.fillRect(Math.min(x1, x2), Math.min(y1, y2), Math.abs(x2 - x1), Math.abs(y2 - y1))
  }
  const spread = scene.spread
  const rings: [number[][] | undefined, string][] = [
    [spread?.horizon_60s, "#5d7384"],
    [spread?.horizon_30s, "#c6a15b"],
    [spread?.now, "#d4652f"],
  ]
  for (const [ring, color] of rings) {
    if (!ring || ring.length < 2) continue
    ctx.beginPath()
    ring.forEach((item, index) => {
      const [x, y] = point(item[0], item[1])
      if (index === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    })
    ctx.strokeStyle = color
    ctx.stroke()
  }
  for (const camera of scene.cameras) {
    const [x, y] = point(camera.eye[0], camera.eye[1])
    ctx.fillStyle = "#d7e0ea"
    ctx.fillRect(x - 3, y - 3, 6, 6)
  }
  if (scene.fire) {
    const [x, y] = point(scene.fire.xyz[0], scene.fire.xyz[1])
    ctx.fillStyle = "#d4652f"
    ctx.beginPath()
    ctx.arc(x, y, 5, 0, Math.PI * 2)
    ctx.fill()
  }
}

function drawChart() {
  const canvas = chart.value
  const growth = status.value?.analysis?.growth
  if (!canvas) return
  const width = canvas.clientWidth
  const height = canvas.clientHeight
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext("2d")
  if (!ctx) return
  ctx.clearRect(0, 0, width, height)
  const series = growth?.curve?.length ? growth.curve : growth?.samples
  if (!series || series.length < 2) {
    ctx.fillStyle = "#8b9aab"
    ctx.font = "13px sans-serif"
    ctx.fillText(growth?.reason || "热释放曲线还没有足够样本", 12, 28)
    return
  }
  const maxQ = Math.max(...series.map((item) => item.q))
  const maxT = series[series.length - 1].t
  const left = 36
  const bottom = height - 22
  ctx.strokeStyle = "#31404d"
  ctx.beginPath()
  ctx.moveTo(left, 12)
  ctx.lineTo(left, bottom)
  ctx.lineTo(width - 8, bottom)
  ctx.stroke()
  ctx.beginPath()
  series.forEach((item, index) => {
    const x = left + (item.t / maxT) * (width - left - 12)
    const y = bottom - (item.q / maxQ) * (bottom - 16)
    if (index === 0) ctx.moveTo(x, y)
    else ctx.lineTo(x, y)
  })
  ctx.strokeStyle = "#d4652f"
  ctx.lineWidth = 1.6
  ctx.stroke()
  ctx.fillStyle = "#8b9aab"
  ctx.font = "12px sans-serif"
  ctx.fillText("kW", 8, 16)
  ctx.fillText("s", width - 16, height - 6)
}

async function load() {
  status.value = await api<DemoStatus>("/demo")
  drawPlan()
  drawChart()
  await refreshFrames()
}

async function tick() {
  if (busy) return
  busy = true
  try {
    await load()
  } catch (error) {
    ElMessage.error(messageOf(error))
  } finally {
    busy = false
  }
}

async function start(script: string) {
  try {
    await api("/demo/start", { method: "POST", body: JSON.stringify({ script, speed: 1 }) })
    await load()
  } catch (error) {
    ElMessage.error(messageOf(error))
  }
}

async function reset() {
  try {
    status.value = await api<DemoStatus>("/demo/reset", { method: "POST" })
  } catch (error) {
    ElMessage.error(messageOf(error))
  }
}

onMounted(() => {
  fit()
  window.addEventListener("resize", fit)
  timer = window.setInterval(tick, 250)
  void tick()
})

onBeforeUnmount(() => {
  window.clearInterval(timer)
  window.removeEventListener("resize", fit)
  for (const url of Object.values(urls.value)) URL.revokeObjectURL(url)
})
</script>

<template>
  <div class="board-wrap">
    <div ref="stage" class="board">
      <header class="board-head">
        <div>
          <strong>校园智能火情预警</strong>
          <span>{{ status?.room_name || "演示教室" }}</span>
          <span v-if="status?.script_title">{{ status.script_title }}</span>
          <span v-else>尚未开始</span>
        </div>
        <DemoBadge :synthetic="status?.synthetic" />
        <div class="board-clock">{{ clock }}</div>
      </header>
      <section class="board-mid">
        <div class="board-videos">
          <ReplayPane v-for="(camera, index) in cameras" :key="index" :camera="camera" :src="camera ? urls[camera.id] || '' : ''" />
        </div>
        <div class="board-side">
          <section class="board-panel">
            <h2>平面</h2>
            <canvas ref="plan" />
          </section>
          <section class="board-panel chart-panel">
            <h2>
              热释放
              <em v-if="status?.analysis?.growth?.bin">{{ growthLabels[status.analysis.growth.bin] }}</em>
              <em v-if="status?.analysis?.size">{{ status.analysis.size.q_kw.toFixed(1) }} kW</em>
            </h2>
            <canvas ref="chart" />
          </section>
          <section class="board-panel verdict">
            <h2>
              研判
              <em v-if="status?.analysis?.cached">缓存结果</em>
            </h2>
            <p v-if="status?.analysis?.level" class="grade">{{ status.analysis.level.grade }} 级</p>
            <p v-else class="muted">还没有研判结论</p>
            <p v-if="status?.analysis?.evidence">
              {{ status.analysis.evidence.burning_objects.map((item) => item.name).join("、") || "燃烧物未标明" }}
              · {{ causeLabels[status.analysis.evidence.suspected_cause] || status.analysis.evidence.suspected_cause }}
            </p>
            <p v-if="status?.analysis?.rules">
              {{ status.analysis.rules.classes.join(" / ") || "未分类" }}
              · {{ status.analysis.water_prohibited ? "禁止用水" : "可以用水" }}
            </p>
            <p v-if="status?.analysis?.rules?.recommended.length">可用 {{ status.analysis.rules.recommended.join("、") }}</p>
            <p v-if="status?.analysis?.rules?.forbidden.length">禁止 {{ status.analysis.rules.forbidden.join("、") }}</p>
            <p v-if="status?.analysis?.rules?.actions.length">{{ status.analysis.rules.actions.join("；") }}</p>
            <p v-if="status?.analysis?.synthetic_response" class="muted">{{ status.analysis.cache_note }}</p>
          </section>
        </div>
      </section>
      <footer class="board-foot">
        <section class="board-panel timeline">
          <h2>状态</h2>
          <ol>
            <li v-for="(item, index) in shownEvents" :key="index" :class="{ blocked: item.kind === 'SUP_BLOCK' }">
              <span>{{ eventName[item.kind] }}</span>
              <small v-if="item.detail.reason">{{ status?.message || item.detail.reason }}</small>
            </li>
            <li v-if="!shownEvents.length" class="muted">监视</li>
          </ol>
          <div v-if="admin" class="scripts">
            <button
              v-for="script in status?.scripts ?? []"
              :key="script.id"
              type="button"
              :class="{ active: status?.script === script.id }"
              @click="start(script.id)"
            >
              {{ script.title }}
            </button>
            <button type="button" @click="reset">重置</button>
          </div>
        </section>
        <section class="board-panel hardware">
          <h2>执行端</h2>
          <div class="lamp-row">
            <i class="lamp" :class="status?.alarm || 'OFF'" />
            <span>{{ status?.phase || "监视" }}</span>
          </div>
          <p>云台 {{ (status?.actuator.pan_deg ?? 0).toFixed(1) }}° / {{ (status?.actuator.tilt_deg ?? 0).toFixed(1) }}°</p>
          <p>激光 {{ status?.actuator.laser === "ON" ? "开" : "关" }}</p>
          <p v-if="status && !status.pump_run" class="hold">水泵已禁用</p>
          <p v-else>水泵 {{ status?.actuator.pump === "ON" ? "运行" : "停止" }}</p>
          <p class="muted">{{ status?.hardware === "serial" ? "串口硬件" : "模拟硬件" }} · {{ status?.detector === "model" ? "模型检测" : "检测框回放" }}</p>
        </section>
        <section class="board-panel twin-panel">
          <h2>孪生</h2>
          <TwinScene :scene="status?.scene ?? null" still />
        </section>
      </footer>
    </div>
  </div>
</template>
