import type { CameraStatus, IncidentStatus, PrimaryType, SceneType, Severity, SourceType } from '@/types/domain'

export const severityLabels: Record<Severity, string> = {
  LOW: '低风险',
  MEDIUM: '中风险',
  HIGH: '高风险',
  CRITICAL: '严重',
}

export const statusLabels: Record<IncidentStatus, string> = {
  NEW: '待确认',
  ACKNOWLEDGED: '已确认',
  HANDLING: '处置中',
  RESOLVED: '已解决',
  FALSE_ALARM: '误报',
}

export const cameraStatusLabels: Record<CameraStatus, string> = {
  ONLINE: '在线',
  OFFLINE: '离线',
  DEGRADED: '降级',
  UNKNOWN: '未知',
}

export const sceneLabels: Record<SceneType, string> = {
  CLASSROOM: '教室',
  LABORATORY: '实验室',
  CORRIDOR: '走廊',
  OTHER: '其他',
}

export const sourceLabels: Record<SourceType, string> = {
  INTEGRATED: '内置摄像头',
  USB: 'USB 摄像头',
  NETWORK_RTSP: '网络摄像头',
  DEMO_FILE: '演示视频',
}

export const primaryTypeLabels: Record<PrimaryType, string> = {
  FIRE: '火焰',
  SMOKE: '烟雾',
  FIRE_AND_SMOKE: '火焰与烟雾',
}

export const severityOrder: Record<Severity, number> = { LOW: 0, MEDIUM: 1, HIGH: 2, CRITICAL: 3 }
