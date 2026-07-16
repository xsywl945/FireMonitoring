<template>
  <div ref="chartEl" class="trend-chart" role="img" aria-label="最近七小时火焰和烟雾检测趋势图" />
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { TrendPoint } from '@/types/domain'

echarts.use([LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

const props = defineProps<{ data: TrendPoint[] }>()
const chartEl = ref<HTMLDivElement>()
let chart: echarts.ECharts | undefined
let resizeObserver: ResizeObserver | undefined

function render() {
  chart?.setOption({
    color: ['#ff6b3d', '#4bb8ff'],
    tooltip: { trigger: 'axis', backgroundColor: '#102536', borderColor: '#26465d', textStyle: { color: '#ecf7ff' } },
    legend: { right: 2, top: 0, textStyle: { color: '#8fa8b8' }, data: ['火焰', '烟雾'] },
    grid: { left: 14, right: 12, top: 42, bottom: 6, containLabel: true },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: props.data.map((item) => item.label),
      axisLine: { lineStyle: { color: '#264355' } },
      axisLabel: { color: '#708b9c' },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      splitLine: { lineStyle: { color: 'rgba(92, 128, 150, .12)' } },
      axisLabel: { color: '#708b9c' },
    },
    series: [
      {
        name: '火焰',
        type: 'line',
        smooth: 0.35,
        symbol: 'circle',
        symbolSize: 7,
        lineStyle: { width: 3 },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(255,107,61,.28)' }, { offset: 1, color: 'rgba(255,107,61,0)' }]) },
        data: props.data.map((item) => item.fire),
      },
      {
        name: '烟雾',
        type: 'line',
        smooth: 0.35,
        symbol: 'circle',
        symbolSize: 7,
        lineStyle: { width: 3 },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(75,184,255,.18)' }, { offset: 1, color: 'rgba(75,184,255,0)' }]) },
        data: props.data.map((item) => item.smoke),
      },
    ],
  })
}

onMounted(() => {
  if (!chartEl.value) return
  chart = echarts.init(chartEl.value)
  render()
  resizeObserver = new ResizeObserver(() => chart?.resize())
  resizeObserver.observe(chartEl.value)
})

watch(() => props.data, render, { deep: true })
onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  chart?.dispose()
})
</script>
