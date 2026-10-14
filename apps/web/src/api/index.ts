import { http, isMockMode } from './client'
import { mockCameras, mockIncidentDetails, mockIncidents, mockZones } from './mockData'
import type {
  AuthResponse,
  Camera,
  LocalCameraDevice,
  CameraBinding,
  CameraProbeResult,
  CameraUpsert,
  IncidentActionRequest,
  IncidentDetail,
  IncidentQuery,
  IncidentSummary,
  IncidentAnalysis,
  InferenceLiveStatus,
  InferenceRuntime,
  InferenceConfig,
  StreamTicket,
  User,
  Zone,
  ZoneUpsert,
} from '@/types/domain'

const wait = (ms = 220) => new Promise((resolve) => setTimeout(resolve, ms))
const clone = <T>(value: T): T => structuredClone(value)

export const authApi = {
  async login(username: string, password: string): Promise<AuthResponse> {
    if (isMockMode) {
      await wait(420)
      if (username !== 'admin' || password !== '123456') throw new Error('用户名或密码不正确')
      return {
        accessToken: 'mock-jwt-for-local-demo',
        expiresInSeconds: 28_800,
        user: { id: 1, username, displayName: '石旭生', roles: ['ADMIN', 'OPERATOR'] },
      }
    }
    return (await http.post<AuthResponse>('/auth/login', { username, password })).data
  },
  async me(): Promise<User> {
    if (isMockMode) {
      await wait(80)
      return { id: 1, username: 'admin', displayName: '石旭生', roles: ['ADMIN', 'OPERATOR'] }
    }
    return (await http.get<User>('/users/me')).data
  },
}

export const zoneApi = {
  async update(id: number, input: ZoneUpsert): Promise<Zone> {
    if (isMockMode) {
      const zone = mockZones.find((item) => item.id === id)
      if (!zone) throw new Error('教室不存在')
      if (mockZones.some((item) => item.id !== id && item.name === input.name.trim())) throw new Error('教室名称已存在')
      Object.assign(zone, input, { name: input.name.trim() })
      mockIncidentDetails.filter((item) => item.zoneId === id).forEach((item) => { item.zoneName = zone.name })
      mockIncidents.filter((item) => item.zoneId === id).forEach((item) => { item.zoneName = zone.name })
      return clone(zone)
    }
    return (await http.put<Zone>(`/zones/${id}`, input)).data
  },
  async delete(id: number): Promise<void> {
    if (isMockMode) {
      const zone = mockZones.find((item) => item.id === id)
      if (zone) {
        if (mockIncidents.some((item) => item.zoneId === id)) zone.status = 'DISABLED'
        else mockZones.splice(mockZones.indexOf(zone), 1)
      }
      mockCameras.filter((item) => item.zoneId === id).forEach((item) => { delete item.zoneId; delete item.viewRole })
      return
    }
    await http.delete(`/zones/${id}`)
  },
  async list(): Promise<Zone[]> {
    if (isMockMode) return clone(mockZones.filter((item) => item.status === 'ENABLED'))
    return (await http.get<Zone[]>('/zones')).data
  },
  async create(input: ZoneUpsert): Promise<Zone> {
    if (isMockMode) {
      await wait()
      if (mockZones.some((item) => item.name === input.name.trim())) throw new Error('教室名称已存在')
      const zone: Zone = { ...input, name: input.name.trim(), id: Date.now(), status: 'ENABLED' }
      mockZones.push(zone)
      return clone(zone)
    }
    return (await http.post<Zone>('/zones', input)).data
  },
  async replaceBindings(zoneId: number, bindings: CameraBinding[]): Promise<void> {
    if (isMockMode) {
      await wait()
      if (bindings.some((binding) => mockCameras.some((camera) => camera.id === binding.cameraId && camera.zoneId && camera.zoneId !== zoneId))) throw new Error('摄像头已绑定其他教室，请先解除绑定')
      mockCameras.forEach((camera) => {
        if (camera.zoneId === zoneId) {
          delete camera.zoneId
          delete camera.viewRole
        }
      })
      bindings.forEach((binding) => {
        const camera = mockCameras.find((item) => item.id === binding.cameraId)
        if (camera) {
          camera.zoneId = zoneId
          camera.viewRole = binding.viewRole
        }
      })
      return
    }
    await http.put(`/zones/${zoneId}/camera-bindings`, bindings)
  },
}

export const cameraApi = {
  async localDevices(): Promise<LocalCameraDevice[]> {
    if (isMockMode) return [{ index: 0, name: '前置摄像头（模拟）' }, { index: 1, name: 'USB 摄像头（模拟）' }]
    return (await http.get<LocalCameraDevice[]>('/cameras/local-devices')).data
  },
  async start(id: number): Promise<InferenceRuntime> {
    if (isMockMode) throw new Error('请连接实际服务后启动摄像头')
    return (await http.post<InferenceRuntime>(`/cameras/${id}/start`)).data
  },
  async stop(): Promise<InferenceRuntime> {
    if (isMockMode) throw new Error('当前为模拟模式')
    return (await http.post<InferenceRuntime>('/cameras/local-stop')).data
  },
  async update(id: number, input: CameraUpsert): Promise<Camera> {
    if (isMockMode) {
      const camera = mockCameras.find((item) => item.id === id)
      if (!camera) throw new Error('摄像头不存在')
      Object.assign(camera, { name: input.name, sourceType: input.sourceType, targetFps: input.targetFps, status: 'UNKNOWN', lastSeenAt: null })
      if (input.sourceUri) camera.maskedSource = input.sourceType === 'NETWORK_RTSP' ? 'rtsp://***:***@camera/stream' : input.sourceUri
      return clone(camera)
    }
    return (await http.put<Camera>(`/cameras/${id}`, input)).data
  },
  async delete(id: number): Promise<void> {
    if (isMockMode) {
      const index = mockCameras.findIndex((item) => item.id === id)
      if (index >= 0) mockCameras.splice(index, 1)
      return
    }
    await http.delete(`/cameras/${id}`)
  },
  async list(): Promise<Camera[]> {
    if (isMockMode) return clone(mockCameras)
    return (await http.get<Camera[]>('/cameras')).data
  },
  async create(input: CameraUpsert): Promise<Camera> {
    if (isMockMode) {
      await wait()
      const camera: Camera = {
        id: Date.now(),
        name: input.name,
        targetFps: input.targetFps,
        sourceType: input.sourceType,
        streamKey: `camera-${Date.now()}`,
        maskedSource: input.sourceType === 'NETWORK_RTSP' ? 'rtsp://***:***@camera/stream' : input.sourceUri,
        status: 'UNKNOWN',
        lastSeenAt: null,
      }
      mockCameras.push(camera)
      return clone(camera)
    }
    return (await http.post<Camera>('/cameras', input)).data
  },
  async probe(cameraId: number): Promise<CameraProbeResult> {
    if (isMockMode) {
      await wait(650)
      const camera = mockCameras.find((item) => item.id === cameraId)

      return { reachable: false, configurationValid: Boolean(camera), checkedAt: new Date().toISOString(), message: '配置有效，连接状态以视频画面为准' }
    }
    return (await http.post<CameraProbeResult>(`/cameras/${cameraId}/probe`)).data
  },
  async streamTicket(cameraId: number): Promise<StreamTicket> {
    if (isMockMode) {
      await wait(100)
      return {
        expiresAt: new Date(Date.now() + 60_000).toISOString(),
        whepUrl: '',
        hlsUrl: '',
      }
    }
    return (await http.post<StreamTicket>(`/cameras/${cameraId}/stream-ticket`)).data
  },
}

export const incidentApi = {
  async analyses(): Promise<IncidentAnalysis[]> {
    if (isMockMode) return clone(mockIncidentDetails.map((detail) => ({ incident: detail, semanticAnalysis: detail.semanticAnalysis })))
    return (await http.get<IncidentAnalysis[]>('/incidents/analyses')).data
  },
  async list(query: IncidentQuery = {}): Promise<IncidentSummary[]> {
    if (isMockMode) {
      await wait(120)
      return clone(
        mockIncidents.filter(
          (incident) => (!query.status || incident.status === query.status) && (!query.severity || incident.severity === query.severity),
        ),
      )
    }
    return (await http.get<IncidentSummary[]>('/incidents', { params: query })).data
  },
  async get(incidentId: number): Promise<IncidentDetail> {
    if (isMockMode) {
      await wait(150)
      const detail = mockIncidentDetails.find((item) => item.id === incidentId)
      if (!detail) throw new Error('事件不存在')
      return clone(detail)
    }
    return (await http.get<IncidentDetail>(`/incidents/${incidentId}`)).data
  },
  async transition(incidentId: number, input: IncidentActionRequest): Promise<IncidentDetail> {
    if (isMockMode) {
      await wait(280)
      const detail = mockIncidentDetails.find((item) => item.id === incidentId)
      const summary = mockIncidents.find((item) => item.id === incidentId)
      if (!detail || !summary) throw new Error('事件不存在')
      const statusMap = {
        ACKNOWLEDGE: 'ACKNOWLEDGED',
        START_HANDLING: 'HANDLING',
        RESOLVE: 'RESOLVED',
        MARK_FALSE_ALARM: 'FALSE_ALARM',
      } as const
      detail.status = statusMap[input.action]
      summary.status = detail.status
      if (input.action === 'ACKNOWLEDGE') {
        detail.acknowledgedAt = new Date().toISOString()
        summary.acknowledgedAt = detail.acknowledgedAt
      }
      detail.timeline.unshift({
        id: crypto.randomUUID(),
        action: input.action === 'MARK_FALSE_ALARM' ? '标记误报' : input.action === 'RESOLVE' ? '事件解决' : input.action === 'ACKNOWLEDGE' ? '人工确认' : '开始处置',
        actor: '石旭生',
        note: input.note,
        occurredAt: new Date().toISOString(),
      })
      return clone(detail)
    }
    return (
      await http.post<IncidentDetail>(`/incidents/${incidentId}/actions`, input, {
        headers: { 'Idempotency-Key': crypto.randomUUID() },
      })
    ).data
  },
  async evidence(incidentId: number, index: number): Promise<Blob> {
    return (await http.get<Blob>(`/incidents/${incidentId}/evidence/${index}`, { responseType: 'blob' })).data
  },
}

async function inferenceGet<T>(path: string): Promise<T> {
  const response = await fetch(`/inference/api/v1${path}`, { cache: 'no-store', signal: AbortSignal.timeout(5000) })
  if (!response.ok) throw new Error(`推理服务请求失败 (${response.status})`)
  return response.json() as Promise<T>
}

export const inferenceApi = {
  config: () => inferenceGet<InferenceConfig>('/config'),
  runtime: () => inferenceGet<InferenceRuntime>('/runtime'),
  liveStatus: () => inferenceGet<InferenceLiveStatus>('/live/status'),
}
