<template>
  <article class="stream-card" :class="{ 'stream-offline': camera.status === 'OFFLINE' }">
    <div class="stream-stage">
      <img
        v-if="mode === 'inference'"
        class="inference-feed"
        :src="inferenceStreamUrl"
        alt="本地摄像头实时检测画面"
        @error="handleInferenceError"
      />
      <video v-else ref="videoEl" muted autoplay playsinline />
      <div v-if="mode === 'mock'" class="mock-feed" aria-label="模拟视频流占位画面">
        <div class="mock-room">
          <div class="mock-window" />
          <div class="mock-board" />
          <div class="mock-desk mock-desk-one" />
          <div class="mock-desk mock-desk-two" />
          <div class="mock-desk mock-desk-three" />
        </div>
        <div class="scan-line" />
        <div class="mock-label">演示流占位 · 等待本地采集服务</div>
      </div>
      <div v-else-if="mode === 'loading'" class="stream-message">
        <div class="signal-loader"><span /><span /><span /></div>
        <strong>正在建立视频连接</strong>
        <small>优先尝试低延迟 WebRTC</small>
      </div>
      <div v-else-if="mode === 'offline' || mode === 'error'" class="stream-message">
        <div class="offline-symbol"><i /><i /></div>
        <strong>{{ camera.status === 'OFFLINE' ? '摄像头离线' : '暂时无法播放视频' }}</strong>
        <small>{{ errorMessage || '请检查采集服务和媒体网关' }}</small>
        <el-button size="small" plain @click="connect">重新连接</el-button>
      </div>

      <div class="stream-topline">
        <span class="view-role">{{ camera.viewRole || '未绑定视角' }}</span>
        <span class="live-indicator" :class="{ active: camera.status === 'ONLINE' }">
          <i /> {{ camera.status === 'ONLINE' ? 'LIVE' : cameraStatusLabels[camera.status] }}
        </span>
      </div>
      <div class="stream-telemetry">
        <span>{{ mode === 'inference' ? 'LOCAL YOLO' : mode === 'webrtc' ? 'WebRTC' : mode === 'hls' ? 'HLS' : 'LOCAL DEMO' }}</span>
        <span>{{ mode === 'inference' ? '检测框已叠加' : '实时视频' }}</span>
        <span>推理 5 FPS</span>
      </div>
    </div>
    <footer class="stream-footer">
      <div>
        <strong>{{ camera.name }}</strong>
        <span>{{ camera.maskedSource || sourceLabels[camera.sourceType] }}</span>
      </div>
      <div class="camera-pulse"><span /> 视频源正常</div>
    </footer>
  </article>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import Hls from 'hls.js'
import { cameraApi } from '@/api'
import { isMockMode } from '@/api/client'
import { cameraStatusLabels, sourceLabels } from '@/config/labels'
import type { Camera } from '@/types/domain'

const props = defineProps<{ camera: Camera }>()
type PlaybackMode = 'loading' | 'mock' | 'inference' | 'webrtc' | 'hls' | 'offline' | 'error'
const videoEl = ref<HTMLVideoElement>()
const mode = ref<PlaybackMode>('loading')
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
  if (props.camera.status === 'OFFLINE') {
    mode.value = 'offline'
    return
  }
  if (isMockMode) {
    mode.value = 'mock'
    return
  }
  if (import.meta.env.VITE_SINGLE_CAMERA_INFERENCE === 'true') {
    mode.value = 'inference'
    return
  }
  mode.value = 'loading'
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
  errorMessage.value = '本地推理画面尚未就绪，请确认推理服务和摄像头已启动'
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

onMounted(connect)
onBeforeUnmount(cleanup)
</script>
