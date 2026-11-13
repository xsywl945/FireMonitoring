<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from "vue"
import type { LiveCamera } from "../api/types"
import { stateLabels } from "../labels"

const props = defineProps<{ camera: LiveCamera | null }>()
const videoRef = ref<HTMLVideoElement | null>(null)
const canvasRef = ref<HTMLCanvasElement | null>(null)
const failure = ref("")
let peer: RTCPeerConnection | null = null
let observer: ResizeObserver | null = null

function closePeer() {
  peer?.close()
  peer = null
  if (videoRef.value) videoRef.value.srcObject = null
}

function waitIce(pc: RTCPeerConnection) {
  if (pc.iceGatheringState === "complete") return Promise.resolve()
  return new Promise<void>((resolve) => {
    const timer = window.setTimeout(resolve, 800)
    pc.addEventListener("icegatheringstatechange", () => {
      if (pc.iceGatheringState === "complete") {
        window.clearTimeout(timer)
        resolve()
      }
    })
  })
}

async function connect() {
  closePeer()
  failure.value = ""
  const camera = props.camera
  if (!camera) return
  const pc = new RTCPeerConnection()
  peer = pc
  pc.addTransceiver("video", { direction: "recvonly" })
  pc.ontrack = (event) => {
    if (videoRef.value) videoRef.value.srcObject = event.streams[0] ?? null
  }
  const offer = await pc.createOffer()
  await pc.setLocalDescription(offer)
  await waitIce(pc)
  const response = await fetch(camera.whep_url, {
    method: "POST",
    headers: { "Content-Type": "application/sdp" },
    body: pc.localDescription?.sdp ?? "",
  })
  if (!response.ok) throw new Error(`无画面（${response.status}）`)
  await pc.setRemoteDescription({ type: "answer", sdp: await response.text() })
  await videoRef.value?.play()
}

function draw() {
  const canvas = canvasRef.value
  const camera = props.camera
  if (!canvas || !camera) return
  const bounds = canvas.getBoundingClientRect()
  canvas.width = bounds.width
  canvas.height = bounds.height
  const ctx = canvas.getContext("2d")
  if (!ctx || !camera.width || !camera.height) return
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  const scale = Math.min(canvas.width / camera.width, canvas.height / camera.height)
  const offsetX = (canvas.width - camera.width * scale) / 2
  const offsetY = (canvas.height - camera.height * scale) / 2
  for (const det of camera.detections) {
    const [x1, y1, x2, y2] = det.bbox
    ctx.strokeStyle = det.class_name === "fire" ? "#9f2d20" : "#8a5a00"
    ctx.lineWidth = 2
    ctx.strokeRect(offsetX + x1 * scale, offsetY + y1 * scale, (x2 - x1) * scale, (y2 - y1) * scale)
    ctx.fillStyle = ctx.strokeStyle
    ctx.font = "12px sans-serif"
    const label = det.class_name === "fire" ? "火" : "烟"
    ctx.fillText(
      `${label} ${det.confidence.toFixed(2)}`,
      offsetX + x1 * scale,
      Math.max(12, offsetY + y1 * scale - 4),
    )
  }
}

async function start() {
  try {
    await connect()
  } catch (error) {
    failure.value = error instanceof Error ? error.message : "无画面"
  }
  draw()
}

watch(() => props.camera?.whep_url, start)
watch(() => props.camera, draw, { deep: true })

watch(canvasRef, (canvas) => {
  observer?.disconnect()
  if (!canvas) return
  observer = new ResizeObserver(() => draw())
  observer.observe(canvas)
  start()
})

onBeforeUnmount(() => {
  observer?.disconnect()
  closePeer()
})
</script>

<template>
  <article class="cell">
    <div v-if="!camera" class="empty">未绑定</div>
    <template v-else>
      <div class="stage">
        <video ref="videoRef" autoplay muted playsinline />
        <canvas ref="canvasRef" />
      </div>
      <div class="cell-meta">
        <div>{{ camera.name }}</div>
        <div>
          火 {{ stateLabels[camera.states.fire] || camera.states.fire }}
          / 烟 {{ stateLabels[camera.states.smoke] || camera.states.smoke }}
          / {{ camera.online ? "检测在线" : "检测离线" }}
        </div>
        <div v-if="failure">{{ failure }}</div>
      </div>
    </template>
  </article>
</template>
