import type {
  Camera,
  DashboardSummary,
  IncidentDetail,
  IncidentSummary,
  ServiceHealth,
  TrendPoint,
  Zone,
} from '@/types/domain'

const now = Date.now()
const isoAgo = (minutes: number) => new Date(now - minutes * 60_000).toISOString()

export const mockZones: Zone[] = [
  { id: 1, name: '求实楼 301 智慧教室', sceneType: 'CLASSROOM', status: 'ENABLED' },
  { id: 2, name: '求实楼 407 电工实验室', sceneType: 'LABORATORY', status: 'ENABLED' },
]

export const mockCameras: Camera[] = [
  {
    id: 1,
    name: '笔记本前置摄像头',
    sourceType: 'INTEGRATED',
    streamKey: 'classroom-view-a',
    maskedSource: 'Integrated Camera',
    status: 'ONLINE',
    lastSeenAt: isoAgo(0),
    zoneId: 1,
    viewRole: 'VIEW_A',
  },
  {
    id: 2,
    name: 'USB 侧视摄像头',
    sourceType: 'USB',
    streamKey: 'classroom-view-b',
    maskedSource: 'USB Camera #1',
    status: 'ONLINE',
    lastSeenAt: isoAgo(0),
    zoneId: 1,
    viewRole: 'VIEW_B',
  },
]

export const mockIncidentDetails: IncidentDetail[] = [
  {
    id: 24071601,
    zoneId: 1,
    zoneName: '求实楼 301 智慧教室',
    status: 'NEW',
    severity: 'CRITICAL',
    primaryType: 'FIRE_AND_SMOKE',
    startedAt: isoAgo(3),
    acknowledgedAt: null,
    fusionScore: 0.94,
    observations: [
      {
        id: 'obs-a-01',
        viewRole: 'VIEW_A',
        cameraName: '笔记本前置摄像头',
        capturedAt: isoAgo(3),
        temporalScore: 0.92,
        detections: [
          { className: 'fire', confidence: 0.96, bboxXyxy: [176, 240, 348, 431] },
          { className: 'smoke', confidence: 0.87, bboxXyxy: [142, 98, 401, 302] },
        ],
      },
      {
        id: 'obs-b-01',
        viewRole: 'VIEW_B',
        cameraName: 'USB 侧视摄像头',
        capturedAt: isoAgo(3),
        temporalScore: 0.89,
        detections: [{ className: 'fire', confidence: 0.91, bboxXyxy: [221, 214, 389, 438] }],
      },
    ],
    semanticAnalysis: {
      state: 'COMPLETED',
      summary: '两视角均观察到持续明火，伴随向上扩散的灰色烟雾，火源位于讲台右侧桌面附近。',
      sourceNature: '疑似插线板或小型电器起火，当前仅为语义研判，需现场人员确认。',
      sceneRisk: '附近存在纸张、窗帘等可燃物，火势具有向上和侧向蔓延风险。',
      recommendations: ['立即切断对应区域电源', '通知现场人员疏散并联系校内消防值班人员', '仅在确保人身安全时使用适用灭火器'],
      uncertainty: '画面不能确认设备内部是否仍在持续短路。',
      model: 'qwen3-vl-plus',
    },
    timeline: [
      { id: 'tl-1', action: '候选检测', actor: 'YOLO 检测服务', occurredAt: isoAgo(3.4), note: 'VIEW_A 连续 4/5 帧检测到火焰' },
      { id: 'tl-2', action: '双视角确认', actor: '决策融合服务', occurredAt: isoAgo(3.1), note: '500ms 窗口内双路证据一致，融合分 0.94' },
      { id: 'tl-3', action: '事件创建', actor: '系统', occurredAt: isoAgo(3), note: '已触发站内预警，短信进入发送队列' },
      { id: 'tl-4', action: '语义研判完成', actor: 'qwen3-vl-plus', occurredAt: isoAgo(2.6) },
    ],
  },
  {
    id: 24071600,
    zoneId: 2,
    zoneName: '求实楼 407 电工实验室',
    status: 'HANDLING',
    severity: 'HIGH',
    primaryType: 'SMOKE',
    startedAt: isoAgo(46),
    acknowledgedAt: isoAgo(44),
    fusionScore: 0.82,
    observations: [
      {
        id: 'obs-a-02',
        viewRole: 'VIEW_A',
        cameraName: '实验室网络摄像头',
        capturedAt: isoAgo(46),
        temporalScore: 0.86,
        detections: [{ className: 'smoke', confidence: 0.88, bboxXyxy: [110, 86, 372, 324] }],
      },
    ],
    semanticAnalysis: { state: 'PENDING' },
    timeline: [
      { id: 'tl-5', action: '事件创建', actor: '系统', occurredAt: isoAgo(46) },
      { id: 'tl-6', action: '人工确认', actor: '值班员 石旭生', occurredAt: isoAgo(44), note: '已电话联系实验室管理员' },
      { id: 'tl-7', action: '开始处置', actor: '值班员 石旭生', occurredAt: isoAgo(42), note: '现场人员前往确认' },
    ],
  },
  {
    id: 24071512,
    zoneId: 1,
    zoneName: '求实楼 301 智慧教室',
    status: 'RESOLVED',
    severity: 'MEDIUM',
    primaryType: 'SMOKE',
    startedAt: isoAgo(210),
    acknowledgedAt: isoAgo(208),
    fusionScore: 0.71,
    observations: [],
    semanticAnalysis: { state: 'COMPLETED', summary: '少量烟雾已消散，现场已确认无复燃风险。' },
    timeline: [{ id: 'tl-8', action: '事件解决', actor: '管理员', occurredAt: isoAgo(185), note: '演示视频结束，系统恢复正常' }],
  },
  {
    id: 24071508,
    zoneId: 2,
    zoneName: '求实楼 407 电工实验室',
    status: 'FALSE_ALARM',
    severity: 'LOW',
    primaryType: 'SMOKE',
    startedAt: isoAgo(370),
    acknowledgedAt: isoAgo(368),
    fusionScore: 0.48,
    observations: [],
    semanticAnalysis: { state: 'FAILED' },
    timeline: [{ id: 'tl-9', action: '标记误报', actor: '管理员', occurredAt: isoAgo(365), note: '实验水蒸气触发' }],
  },
]

export const mockIncidents: IncidentSummary[] = mockIncidentDetails.map((detail) => ({
  id: detail.id,
  zoneId: detail.zoneId,
  zoneName: detail.zoneName,
  status: detail.status,
  severity: detail.severity,
  primaryType: detail.primaryType,
  startedAt: detail.startedAt,
  acknowledgedAt: detail.acknowledgedAt,
}))

export const mockSummary: DashboardSummary = {
  onlineCameras: 2,
  totalCameras: 2,
  newIncidents: 1,
  handlingIncidents: 1,
  todayIncidents: 4,
}

export const mockTrend: TrendPoint[] = [
  { label: '10:00', fire: 0, smoke: 1 },
  { label: '11:00', fire: 1, smoke: 2 },
  { label: '12:00', fire: 0, smoke: 1 },
  { label: '13:00', fire: 2, smoke: 2 },
  { label: '14:00', fire: 1, smoke: 3 },
  { label: '15:00', fire: 3, smoke: 4 },
  { label: '16:00', fire: 2, smoke: 3 },
]

export const mockServices: ServiceHealth[] = [
  { key: 'api', name: '业务控制服务', description: '认证、事件与设备管理', status: 'HEALTHY', latencyMs: 28, updatedAt: isoAgo(0) },
  { key: 'inference', name: 'AI 推理工作进程', description: 'YOLO · FP16 · 640px · 5 FPS', status: 'HEALTHY', latencyMs: 146, updatedAt: isoAgo(0) },
  { key: 'media', name: '视频媒体网关', description: 'WebRTC / HLS 双通道', status: 'HEALTHY', latencyMs: 37, updatedAt: isoAgo(0) },
  { key: 'redis', name: '实时事件总线', description: 'Redis Streams 消费正常', status: 'HEALTHY', latencyMs: 4, updatedAt: isoAgo(0) },
  { key: 'storage', name: '证据对象存储', description: 'MinIO · 可用空间 163 GB', status: 'HEALTHY', latencyMs: 12, updatedAt: isoAgo(0) },
  { key: 'cloud', name: '云端语义研判', description: 'qwen3-vl-plus · 北京地域', status: 'DEGRADED', latencyMs: 1240, updatedAt: isoAgo(1) },
  { key: 'sms', name: '短信通知', description: '阿里云短信 · 演示白名单', status: 'HEALTHY', latencyMs: 386, updatedAt: isoAgo(3) },
]
