export type Role = 'ADMIN' | 'OPERATOR' | 'VIEWER'
export type Severity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
export type IncidentStatus = 'NEW' | 'ACKNOWLEDGED' | 'HANDLING' | 'RESOLVED' | 'FALSE_ALARM'
export type CameraStatus = 'ONLINE' | 'OFFLINE' | 'DEGRADED' | 'UNKNOWN'
export type SceneType = 'CLASSROOM' | 'LABORATORY' | 'CORRIDOR' | 'OTHER'
export type SourceType = 'INTEGRATED' | 'USB' | 'NETWORK_RTSP' | 'DEMO_FILE'
export type ViewRole = 'VIEW_A' | 'VIEW_B' | 'SINGLE'
export type IncidentAction = 'ACKNOWLEDGE' | 'START_HANDLING' | 'RESOLVE' | 'MARK_FALSE_ALARM'
export type PrimaryType = 'FIRE' | 'SMOKE' | 'FIRE_AND_SMOKE'

export interface User {
  id: number
  username: string
  displayName: string
  roles: Role[]
}

export interface AuthResponse {
  accessToken: string
  expiresInSeconds: number
  user: User
}

export interface DashboardSummary {
  onlineCameras: number
  totalCameras: number
  newIncidents: number
  handlingIncidents: number
  todayIncidents: number
}

export interface Zone {
  id: number
  name: string
  sceneType: SceneType
  status: 'ENABLED' | 'DISABLED'
}

export interface ZoneUpsert {
  name: string
  sceneType: SceneType
}

export interface CameraBinding {
  cameraId: number
  viewRole: ViewRole
  weight: number
}

export interface Camera {
  id: number
  name: string
  sourceType: SourceType
  streamKey: string
  maskedSource?: string
  status: CameraStatus
  lastSeenAt: string | null
  zoneId?: number
  viewRole?: ViewRole
}

export interface CameraUpsert {
  name: string
  sourceType: SourceType
  sourceUri?: string
  targetFps?: number
}

export interface CameraProbeResult {
  reachable: boolean
  checkedAt: string
  width?: number
  height?: number
  fps?: number
  message?: string
}

export interface StreamTicket {
  expiresAt: string
  whepUrl: string
  hlsUrl: string
}

export interface Detection {
  className: 'fire' | 'smoke'
  confidence: number
  bboxXyxy: [number, number, number, number]
}

export interface IncidentSummary {
  id: number
  zoneId: number
  zoneName: string
  status: IncidentStatus
  severity: Severity
  primaryType: PrimaryType
  startedAt: string
  acknowledgedAt?: string | null
}

export interface IncidentObservation {
  id: string
  cameraId: number
  viewRole: ViewRole
  capturedAt: string
  cameraName: string
  imageWidth: number
  imageHeight: number
  snapshotAvailable: boolean
  detections: Detection[]
  temporalScore: number
}

export interface SemanticAnalysis {
  state: 'PENDING' | 'COMPLETED' | 'FAILED'
  summary?: string
  sourceNature?: string
  sceneRisk?: string
  recommendations?: string[]
  uncertainty?: string
  model?: string
  confidence?: number
  errorCode?: string
}

export interface TimelineEntry {
  id: string
  action: string
  actor: string
  note?: string
  occurredAt: string
}

export interface IncidentDetail extends IncidentSummary {
  fusionScore?: number
  observations: IncidentObservation[]
  semanticAnalysis: SemanticAnalysis | null
  timeline: TimelineEntry[]
}

export interface IncidentActionRequest {
  action: IncidentAction
  note?: string
  falseAlarmReason?: 'STEAM' | 'DUST' | 'LIGHT' | 'SCREEN_CONTENT' | 'OTHER'
}

export interface IncidentQuery {
  status?: IncidentStatus
  severity?: Severity
}

export interface TrendPoint {
  label: string
  fire: number
  smoke: number
}

export interface ServiceHealth {
  key: string
  name: string
  description: string
  status: 'HEALTHY' | 'DEGRADED' | 'OFFLINE' | 'UNKNOWN'
  latencyMs?: number
  updatedAt: string
}

export interface InferenceRuntime {
  status: 'IDLE' | 'RUNNING' | 'STOPPED' | 'FAILED'
  modelVersion: string
  framesProcessed: number
  eventsPublished: number
  incidentsConfirmed: number
  lastFrameAt: string | null
  lastError: string | null
}

export interface InferenceLiveStatus {
  ready: boolean
  capturedAt?: string
  imageWidth?: number
  imageHeight?: number
  processTimeMs?: number
  framesProcessed?: number
  detections: Detection[]
}
