import type {
  Camera,
  IncidentDetail,
  IncidentSummary,
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
    streamKey: 'classroom-single',
    maskedSource: '0',
    targetFps: 5,
    status: 'ONLINE',
    lastSeenAt: isoAgo(0),
    zoneId: 1,
    viewRole: 'SINGLE',
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
        cameraId: 1,
        viewRole: 'SINGLE',
        cameraName: '笔记本前置摄像头',
        capturedAt: isoAgo(3),
        temporalScore: 0.92,
        imageWidth: 640,
        imageHeight: 480,
        snapshotAvailable: false,
        detections: [
          { className: 'fire', confidence: 0.96, bboxXyxy: [176, 240, 348, 431] },
          { className: 'smoke', confidence: 0.87, bboxXyxy: [142, 98, 401, 302] },
        ],
      },
    ],
    semanticAnalysis: {
      state: 'COMPLETED',
      summary: '单摄时序帧观察到持续明火，伴随向上扩散的灰色烟雾，火源位于讲台右侧桌面附近。',
      sourceNature: '疑似插线板或小型电器起火，当前仅为语义研判，需现场人员确认。',
      sceneRisk: '附近存在纸张、窗帘等可燃物，火势具有向上和侧向蔓延风险。',
      recommendations: ['立即切断对应区域电源', '通知现场人员疏散并联系校内消防值班人员', '仅在确保人身安全时使用适用灭火器'],
      uncertainty: '画面不能确认设备内部是否仍在持续短路。',
      model: 'qwen3.7-plus',
    },
    timeline: [
      { id: 'tl-1', action: '候选检测', actor: 'YOLO 检测服务', occurredAt: isoAgo(3.4), note: '单摄连续 4/5 帧检测到火焰' },
      { id: 'tl-2', action: '时序确认', actor: '时序证据服务', occurredAt: isoAgo(3.1), note: '单摄时序证据达到确认阈值' },
      { id: 'tl-4', action: '语义研判完成', actor: 'qwen3.7-plus', occurredAt: isoAgo(3.05) },
      { id: 'tl-3', action: '事件创建', actor: '系统', occurredAt: isoAgo(3), note: '多模态复核后发布站内预警' },
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
        cameraId: 3,
        viewRole: 'SINGLE',
        cameraName: '实验室网络摄像头',
        capturedAt: isoAgo(46),
        temporalScore: 0.86,
        imageWidth: 640,
        imageHeight: 480,
        snapshotAvailable: false,
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
