import { http, isMockMode } from './client'
import { mockCameras, mockIncidentDetails, mockIncidents, mockServices, mockSummary, mockTrend, mockZones } from './mockData'
import type {
  AuthResponse,
  Camera,
  CameraBinding,
  CameraProbeResult,
  CameraUpsert,
  DashboardSummary,
  IncidentActionRequest,
  IncidentDetail,
  IncidentQuery,
  IncidentSummary,
  InferenceLiveStatus,
  InferenceRuntime,
  ServiceHealth,
  StreamTicket,
  TrendPoint,
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
      if (!username || password.length < 8) throw new Error('用户名或密码不正确')
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

export const dashboardApi = {
  async summary(): Promise<DashboardSummary> {
    if (isMockMode) return clone(mockSummary)
    return (await http.get<DashboardSummary>('/dashboard/summary')).data
  },
  async trend(): Promise<TrendPoint[]> {
    if (isMockMode) return clone(mockTrend)
    const incidents = await incidentApi.list()
    const counts = new Map<string, TrendPoint>()
    incidents.forEach((incident) => {
      const label = new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit' }).format(new Date(incident.startedAt))
      const current = counts.get(label) || { label, fire: 0, smoke: 0 }
      if (incident.primaryType !== 'SMOKE') current.fire += 1
      if (incident.primaryType !== 'FIRE') current.smoke += 1
      counts.set(label, current)
    })
    return [...counts.values()]
  },
}

export const zoneApi = {
  async list(): Promise<Zone[]> {
    if (isMockMode) return clone(mockZones)
    return (await http.get<Zone[]>('/zones')).data
  },
  async create(input: ZoneUpsert): Promise<Zone> {
    if (isMockMode) {
      await wait()
      const zone: Zone = { ...input, id: Date.now(), status: 'ENABLED' }
      mockZones.push(zone)
      return clone(zone)
    }
    return (await http.post<Zone>('/zones', input)).data
  },
  async replaceBindings(zoneId: number, bindings: CameraBinding[]): Promise<void> {
    if (isMockMode) {
      await wait()
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
      if (camera) {
        camera.status = 'ONLINE'
        camera.lastSeenAt = new Date().toISOString()
      }
      return { reachable: Boolean(camera), checkedAt: new Date().toISOString(), width: 1280, height: 720, fps: 25, message: '视频源连接正常' }
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
  const response = await fetch(`/inference/api/v1${path}`, { cache: 'no-store' })
  if (!response.ok) throw new Error(`推理服务请求失败 (${response.status})`)
  return response.json() as Promise<T>
}

export const inferenceApi = {
  runtime: () => inferenceGet<InferenceRuntime>('/runtime'),
  liveStatus: () => inferenceGet<InferenceLiveStatus>('/live/status'),
}

export const healthApi = {
  async services(): Promise<ServiceHealth[]> {
    if (isMockMode) return clone(mockServices)
    const started = performance.now()
    try {
      await dashboardApi.summary()
      return [
        {
          key: 'api',
          name: '业务控制服务',
          description: 'API 连接正常；其他服务健康信息待后端聚合接口提供',
          status: 'HEALTHY',
          latencyMs: Math.round(performance.now() - started),
          updatedAt: new Date().toISOString(),
        },
      ]
    } catch {
      return [{ key: 'api', name: '业务控制服务', description: '无法访问业务 API', status: 'OFFLINE', updatedAt: new Date().toISOString() }]
    }
  },
}
