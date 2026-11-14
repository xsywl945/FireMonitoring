export interface User {
  id: number
  username: string
  display_name: string
  role: "admin" | "operator"
}

export interface LoginResult {
  access_token: string
  user: User
}

export interface BoundCamera {
  camera_id: number
  slot: number
  name: string
  stream_key: string
  source_type: string
  calibrated: boolean
}

export interface FloorPlan {
  origin_px: number[]
  meters_per_pixel: number
  origin_world_m: number[]
  content_type: string
}

export interface Room {
  id: number
  name: string
  scene_type: string
  cameras: BoundCamera[]
  floor_plan: FloorPlan | null
}

export interface Landmark {
  world_m: number[]
  pixel: number[]
}

export interface Calibration {
  intrinsics: number[][]
  distortion: number[]
  landmarks: Landmark[]
}

export interface Camera {
  id: number
  name: string
  source_type: "USB" | "RTSP"
  source_uri: string
  stream_key: string
  target_fps: number
  calibration: Calibration | null
}

export interface DetectionBox {
  class_name: string
  confidence: number
  bbox: number[]
}

export interface LiveCamera {
  camera_id: number
  slot: number
  name: string
  whep_url: string
  online: boolean
  width: number
  height: number
  states: { fire: string; smoke: string }
  detections: DetectionBox[]
}

export interface LiveState {
  room_id: number
  cameras: LiveCamera[]
}

export interface Position {
  status: string
  xyz?: number[]
  covariance?: number[][]
  condition_number?: number
  support_camera_ids: number[]
}

export interface AlertSummary {
  id: number
  room_id: number
  room_name: string
  alert_type: string
  started_at: string
  position: Position | null
  analysis_status: string | null
}

export interface Analysis {
  status: string
  reasoning_summary: string | null
  risk_level: string | null
  recommended_actions: string[]
  burning_objects: string[]
  people_at_risk: boolean | null
  uncertainties: string[]
  confidence: number | null
  error_code: string | null
  has_visible_fire: boolean | null
  has_visible_smoke: boolean | null
}

export interface FrameInfo {
  camera_id: number
  camera_name: string
  captured_at: string
}

export interface Disposition {
  id: number
  note: string
  actor: string
  occurred_at: string
}

export interface AlertDetail {
  id: number
  room_id: number
  room_name: string
  alert_type: string
  started_at: string
  position: Position | null
  analysis: Analysis | null
  observations: unknown[]
  frames: FrameInfo[]
  dispositions: Disposition[]
  floor_plan: FloorPlan | null
}

export interface PumpStatus {
  enabled: boolean
  deviceState: string
  inhibited: boolean
  lastError: string | null
}
