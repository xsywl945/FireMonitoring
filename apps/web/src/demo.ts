export interface DemoMode {
  enabled: boolean
  label: string
  synthetic?: boolean
  note?: string
}

export interface DemoDetection {
  class_name: string
  confidence: number
  bbox: number[]
}

export interface DemoCamera {
  id: number
  slot: number
  name: string
  key: string
  width: number
  height: number
  detections: DemoDetection[]
}

export interface GrowthPoint {
  t: number
  q: number
}

export interface DemoAnalysis {
  cached?: boolean
  cache_note?: string
  synthetic_response?: boolean
  water_prohibited?: boolean
  level?: { grade: string; reasons: string[] }
  rules?: {
    classes: string[]
    recommended: string[]
    forbidden: string[]
    actions: string[]
    details: { id: string; name: string; reason: string }[]
  }
  growth?: {
    mode: string
    bin?: string
    alpha?: number
    reason?: string
    curve?: GrowthPoint[]
    samples?: GrowthPoint[]
  }
  size?: { q_kw: number; height_m: number; diameter_m: number } | null
  evidence?: { burning_objects: { name: string }[]; suspected_cause: string; person_count: number }
  spread?: {
    status: string
    now?: number[][]
    horizon_30s?: number[][]
    horizon_60s?: number[][]
    speed_m_s?: number
  }
}

export interface SceneFurniture {
  kind: string
  min: number[]
  max: number[]
}

export interface ScenePayload {
  width_m: number
  depth_m: number
  height_m: number
  cameras: {
    name: string
    eye: number[]
    right: number[]
    up: number[]
    forward: number[]
    fov_y_deg: number
  }[]
  fire: { xyz: number[]; radii: number[]; axes: number[][] } | null
  spread: DemoAnalysis["spread"]
  gimbal: {
    p0: number[]
    origin: number[]
    direction: number[]
    pan_cdeg: number
    tilt_cdeg: number
    laser: boolean
    pump: string
  }
  jet: number[][]
  phase: string | null
  alarm: string
  furniture: SceneFurniture[]
}

export interface DemoEvent {
  kind: string
  detail: { phase?: string; reason?: string | null; voice?: string | null }
  occurred_at: string
}

export interface DemoStatus {
  enabled: boolean
  label: string
  synthetic: boolean
  note: string
  hardware: string
  detector: string
  pump_run: boolean
  room_id: number
  room_name: string
  script: string | null
  script_title: string | null
  scripts: { id: string; title: string; duration_s: number }[]
  running: boolean
  finished: boolean
  elapsed_s: number
  duration_s: number | null
  phase: string | null
  block: string | null
  message: string | null
  alarm: string
  cameras: DemoCamera[]
  analysis: DemoAnalysis | null
  position: { status: string; xyz?: number[] } | null
  events: DemoEvent[]
  scene: ScenePayload
  actuator: {
    pump: string
    laser: string
    latch: string
    pan: number
    tilt: number
    pan_deg: number
    tilt_deg: number
    heartbeat: boolean
  }
  error?: string
}

export async function loadDemoMode(): Promise<DemoMode> {
  const response = await fetch("/api/v1/demo/mode")
  if (!response.ok) throw new Error("读不到演示状态")
  return response.json() as Promise<DemoMode>
}
