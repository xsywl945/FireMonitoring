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
  combustibles: { name: string; polygon: number[][] }[]
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
  marker_id?: number
}

export interface Calibration {
  intrinsics: number[][]
  distortion: number[]
  landmarks: Landmark[]
  intrinsics_reprojection_error_px?: number | null
  extrinsics_reprojection_error_px?: number | null
  image_size?: number[] | null
  board?: string | null
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
  health: string
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
  level: string | null
}

export interface BurningObject {
  frame_index: number
  name: string
  evidence: string
}

export interface Analysis {
  status: string
  evidence: {
    burning_objects: BurningObject[]
    suspected_cause: string
    person_count: number
    person_location: string
    smoke_color: string
    smoke_density: string
    uncertainties: string[]
    scene_type: string
  } | null
  rules: {
    classes: string[]
    details: { id: string; name: string; reason: string }[]
    recommended: string[]
    forbidden: string[]
    actions: string[]
    water_prohibited: boolean
    basis: string[]
  }
  scene: {
    configured: string
    configured_label: string
    observed: string | null
    observed_label: string | null
    mismatch: boolean
  }
  size: {
    height_m: number
    diameter_m: number
    q_kw: number
    estimated: boolean
  } | null
  growth: {
    mode: string
    bin?: string
    alpha?: number
    seconds_to_100kw?: number
    seconds_to_500kw?: number
    doubling_time_s?: number
    area_rate_px2_per_s?: number
    samples?: { t: number; q?: number; area?: number }[]
    curve?: { t: number; q: number }[]
    reason: string
  }
  level: { grade: string; score: number; reasons: string[] }
  spread: {
    status: string
    now?: number[][]
    horizon_30s?: number[][]
    horizon_60s?: number[][]
    speed_m_s?: number
    direction_deg?: number
    hits?: { name: string; horizon_s: number }[]
  }
  texts: {
    oled: string
    sms_location: string
    sms_level: string
    sms_method: string
  }
  error_code: string | null
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
