<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from "vue"
import { fetchBlob } from "../api/client"
import type { FloorPlan, Position } from "../api/types"

const props = defineProps<{
  roomId: number
  plan: FloorPlan
  position: Position | null
}>()

const url = ref("")
const size = ref({ width: 0, height: 0 })
const point = ref<{ left: number; top: number } | null>(null)

function place() {
  const xyz = props.position?.status === "ESTIMATED" ? props.position.xyz : undefined
  if (!xyz || !size.value.width) {
    point.value = null
    return
  }
  const u = props.plan.origin_px[0] + (xyz[0] - props.plan.origin_world_m[0]) / props.plan.meters_per_pixel
  const v = props.plan.origin_px[1] - (xyz[1] - props.plan.origin_world_m[1]) / props.plan.meters_per_pixel
  point.value = { left: (u / size.value.width) * 100, top: (v / size.value.height) * 100 }
}

function onLoad(event: Event) {
  const image = event.target as HTMLImageElement
  size.value = { width: image.naturalWidth, height: image.naturalHeight }
  place()
}

async function load() {
  if (url.value) URL.revokeObjectURL(url.value)
  url.value = await fetchBlob(`/rooms/${props.roomId}/floor-plan`)
}

watch(() => [props.roomId, props.plan] as const, load, { immediate: true })
watch(() => props.position, place)
onBeforeUnmount(() => {
  if (url.value) URL.revokeObjectURL(url.value)
})
</script>

<template>
  <div class="plan">
    <img v-if="url" :src="url" alt="教室平面图" @load="onLoad" />
    <span v-if="point" class="mark" :style="{ left: `${point.left}%`, top: `${point.top}%` }" />
  </div>
</template>
