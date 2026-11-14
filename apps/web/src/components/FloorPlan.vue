<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { fetchBlob } from "../api/client"
import type { FloorPlan, Position } from "../api/types"

export interface PlanShape {
  points: number[][]
  stroke: string
  fill: string
}

const props = defineProps<{
  roomId: number
  plan: FloorPlan
  position: Position | null
  shapes?: PlanShape[]
  picking?: boolean
}>()

const emit = defineEmits<{ pick: [point: number[]] }>()

const url = ref("")
const size = ref({ width: 0, height: 0 })

const point = computed(() => {
  const xyz = props.position?.status === "ESTIMATED" ? props.position.xyz : undefined
  if (!xyz || !size.value.width) return null
  return toPercent(xyz[0], xyz[1])
})

const polygons = computed(() => {
  if (!size.value.width) return []
  return (props.shapes ?? []).map((shape) => ({
    ...shape,
    points: shape.points.map((item) => toPercent(item[0], item[1])),
  }))
})

function toPercent(x: number, y: number) {
  const u = props.plan.origin_px[0] + (x - props.plan.origin_world_m[0]) / props.plan.meters_per_pixel
  const v = props.plan.origin_px[1] - (y - props.plan.origin_world_m[1]) / props.plan.meters_per_pixel
  return {
    x: (u / size.value.width) * 100,
    y: (v / size.value.height) * 100,
  }
}

function onLoad(event: Event) {
  const image = event.target as HTMLImageElement
  size.value = { width: image.naturalWidth, height: image.naturalHeight }
}

function onClick(event: MouseEvent) {
  if (!props.picking || !size.value.width) return
  const image = event.currentTarget as HTMLImageElement
  const rect = image.getBoundingClientRect()
  const u = ((event.clientX - rect.left) / rect.width) * size.value.width
  const v = ((event.clientY - rect.top) / rect.height) * size.value.height
  const x = props.plan.origin_world_m[0] + (u - props.plan.origin_px[0]) * props.plan.meters_per_pixel
  const y = props.plan.origin_world_m[1] + (props.plan.origin_px[1] - v) * props.plan.meters_per_pixel
  emit("pick", [x, y])
}

async function load() {
  if (url.value) URL.revokeObjectURL(url.value)
  url.value = await fetchBlob(`/rooms/${props.roomId}/floor-plan`)
}

watch(() => [props.roomId, props.plan] as const, load, { immediate: true })
onBeforeUnmount(() => {
  if (url.value) URL.revokeObjectURL(url.value)
})
</script>

<template>
  <div class="plan">
    <img v-if="url" :src="url" alt="平面图" @load="onLoad" @click="onClick" />
    <svg v-if="size.width" class="overlay" viewBox="0 0 100 100" preserveAspectRatio="none">
      <template v-for="(shape, index) in polygons" :key="index">
        <polyline
          v-if="shape.points.length === 2"
          :points="shape.points.map((item) => `${item.x},${item.y}`).join(' ')"
          :stroke="shape.stroke"
          fill="none"
          stroke-width="1.2"
          vector-effect="non-scaling-stroke"
        />
        <polygon
          v-else
          :points="shape.points.map((item) => `${item.x},${item.y}`).join(' ')"
          :stroke="shape.stroke"
          :fill="shape.fill"
          stroke-width="1.2"
          vector-effect="non-scaling-stroke"
        />
      </template>
    </svg>
    <span v-if="point" class="mark" :style="{ left: `${point.x}%`, top: `${point.y}%` }" />
  </div>
</template>
