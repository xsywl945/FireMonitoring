<script setup lang="ts">
import { onMounted, ref, watch } from "vue"
import type { DemoCamera } from "../demo"

const props = defineProps<{ camera: DemoCamera | null; src: string }>()
const canvas = ref<HTMLCanvasElement | null>(null)

function draw() {
  const surface = canvas.value
  const camera = props.camera
  if (!surface || !camera) return
  const bounds = surface.getBoundingClientRect()
  surface.width = bounds.width
  surface.height = bounds.height
  const ctx = surface.getContext("2d")
  if (!ctx || !camera.width || !camera.height) return
  ctx.clearRect(0, 0, surface.width, surface.height)
  const scale = Math.min(surface.width / camera.width, surface.height / camera.height)
  const offsetX = (surface.width - camera.width * scale) / 2
  const offsetY = (surface.height - camera.height * scale) / 2
  for (const det of camera.detections) {
    const [x1, y1, x2, y2] = det.bbox
    ctx.strokeStyle = det.class_name === "fire" ? "#d4652f" : det.class_name === "person" ? "#d7e0ea" : "#9aa7b4"
    ctx.lineWidth = 1.5
    ctx.strokeRect(offsetX + x1 * scale, offsetY + y1 * scale, (x2 - x1) * scale, (y2 - y1) * scale)
  }
}

watch(() => props.camera, draw, { deep: true })
watch(() => props.src, draw)
onMounted(draw)
</script>

<template>
  <article class="replay">
    <div class="replay-stage">
      <img v-if="src" :src="src" alt="回放画面" @load="draw" />
      <div v-else class="replay-wait">等待回放</div>
      <canvas ref="canvas" />
      <div class="replay-tag">回放 · {{ camera?.name || "未绑定" }}</div>
    </div>
  </article>
</template>
