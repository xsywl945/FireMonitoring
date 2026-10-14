<template>
  <article class="stream-card" :class="{ 'stream-offline': camera.status === 'OFFLINE' }">
    <div class="stream-stage">
      <img
        v-if="mode === 'inference'"
        class="inference-feed"
        :src="inferenceStreamUrl"
        alt="本地摄像头实时检测画面"
        @load="inferenceReady = true"
        @error="handleInferenceError"
      />
      <video v-else ref="videoEl" muted autoplay playsinline />
      <div v-if="mode === 'inference' && !inferenceReady" class="stream-message">摄像头启动中…</div>
      <div v-if="mode === 'mock'" class="stream-message">模拟数据模式 · 无实际摄像头画面</div>
      <div v-else-if="mode === 'loading'" class="stream-message">
        <div class="signal-loader"><span /><span /><span /></div>
        <strong>连接中…</strong>

      </div>
      <div v-else-if="mode === 'offline' || mode === 'error'" class="stream-message">
        <div class="offline-symbol"><i /><i /></div>
        <strong>{{ camera.status === 'OFFLINE' ? '摄像头离线' : '视频未接通' }}</strong>
        <small>{{ errorMessage || '请检查采集服务' }}</small>
        <el-button size="small" plain @click="connect">重新连接</el-button>
      </div>

      <div class="stream-topline">

        <span class="live-indicator" :class="{ active: camera.status === 'ONLINE' }">
          <i /> {{ mode === 'mock' ? '模拟数据' : mode === 'error' || mode === 'offline' ? '不可用' : mode === 'loading' ? '连接中' : '视频流' }}
        </span>
      </div>
      <div class="stream-telemetry">
        <span>{{ mode === 'inference' ? 'LOCAL YOLO' : mode === 'webrtc' ? 'WebRTC' : mode === 'hls' ? 'HLS' : 'LOCAL DEMO' }}</span>
        <span>{{ mode === 'mock' ? '无实际视频' : mode === 'inference' ? '检测框已叠加' : '视频画面' }}</span>

      </div>
    </div>
    <footer class="stream-footer">
      <div>
        <strong>{{ camera.name }}</strong>
        <span>{{ sourceLabels[camera.sourceType] }}</span>
      </div>
      <div class="muted">{{ mode === 'mock' ? '模拟画面' : mode === 'error' || mode === 'offline' ? '视频不可用' : mode === 'loading' || mode === 'inference' && !inferenceReady ? '连接中' : '视频已连接' }}</div>
    </footer>
  </article>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch, nextTick } from 'vue'
import Hls from 'hls.js'
import { cameraApi } from '@/api'
import { isMockMode } from '@/api/client'
import { sourceLabels } from '@/config/labels'
import type { Camera } from '@/types/domain'

const props = defineProps<{ camera: Camera; useInference?: boolean }>()
type PlaybackMode = 'loading' | 'mock' | 'inference' | 'webrtc' | 'hls' | 'offline' | 'error'
const videoEl = ref<HTMLVideoElement>()
const mode = ref<PlaybackMode>('loading')
const inferenceReady = ref(false)
const errorMessage = ref('')
const inferenceStreamUrl = '/inference/api/v1/live/stream.mjpg'
let peer: RTCPeerConnection | undefined
let hls: Hls | undefined

function waitIceGathering(connection: RTCPeerConnection) {
  if (connection.iceGatheringState === 'complete') return Promise.resolve()
  return new Promise<void>((resolve) => {
    const timeout = window.setTimeout(resolve, 2_500)
    connection.addEventListener('icegatheringstatechange', () => {
      if (connection.iceGatheringState === 'complete') {
        window.clearTimeout(timeout)
        resolve()
      }
    })
  })
}

async function startWhep(url: string) {
  if (!videoEl.value) throw new Error('播放器未就绪')
  peer = new RTCPeerConnection()
  peer.addTransceiver('video', { direction: 'recvonly' })
  peer.addTransceiver('audio', { direction: 'recvonly' })
  peer.ontrack = (event) => {
    if (videoEl.value) videoEl.value.srcObject = event.streams[0]
  }
  const offer = await peer.createOffer()
  await peer.setLocalDescription(offer)
  await waitIceGathering(peer)
  const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/sdp' }, body: peer.localDescription?.sdp })
  if (!response.ok) throw new Error(`WebRTC 建连失败 (${response.status})`)
  await peer.setRemoteDescription({ type: 'answer', sdp: await response.text() })
  mode.value = 'webrtc'
}

async function startHls(url: string) {
  if (!videoEl.value || !url) throw new Error('没有可用的 HLS 备用地址')
  if (videoEl.value.canPlayType('application/vnd.apple.mpegurl')) {
    videoEl.value.src = url
  } else if (Hls.isSupported()) {
    hls = new Hls({ lowLatencyMode: true, liveSyncDurationCount: 2 })
    hls.loadSource(url)
    hls.attachMedia(videoEl.value)
  } else {
    throw new Error('当前浏览器不支持 HLS')
  }
  await videoEl.value.play()
  mode.value = 'hls'
}

async function connect() {
  cleanup()
  errorMessage.value = ''
  inferenceReady.value = false
  if (props.camera.status === 'OFFLINE') {
    mode.value = 'offline'
    return
  }
  if (isMockMode) {
    mode.value = 'mock'
    return
  }
  if (props.useInference) {
    mode.value = 'inference'
    return
  }
  mode.value = 'loading'
  await nextTick()
  try {
    const ticket = await cameraApi.streamTicket(props.camera.id)
    try {
      await startWhep(ticket.whepUrl)
    } catch {
      await startHls(ticket.hlsUrl)
    }
  } catch (error) {
    mode.value = 'error'
    errorMessage.value = error instanceof Error ? error.message : '视频连接失败'
  }
}

function handleInferenceError() {
  mode.value = 'error'
  errorMessage.value = '摄像头画面未就绪'
}

function cleanup() {
  peer?.close()
  peer = undefined
  hls?.destroy()
  hls = undefined
  if (videoEl.value) {
    videoEl.value.pause()
    videoEl.value.srcObject = null
    videoEl.value.removeAttribute('src')
  }
}

watch(() => props.useInference, connect)
onMounted(connect)
onBeforeUnmount(cleanup)
</script>
