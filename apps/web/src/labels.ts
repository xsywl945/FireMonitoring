export const sceneLabels: Record<string, string> = {
  classroom: "教室",
  laboratory: "实验室",
  corridor: "走廊",
  other: "其他",
}

export const alertLabels: Record<string, string> = {
  FIRE: "火焰",
  SMOKE: "烟雾",
  FIRE_AND_SMOKE: "火焰和烟雾",
}

export const stateLabels: Record<string, string> = {
  NORMAL: "正常",
  SUSPECT: "疑似",
  CONFIRMED: "已确认",
  COOLDOWN: "冷却",
}

export const roleLabels: Record<string, string> = {
  admin: "管理员",
  operator: "值班员",
}

export function formatTime(value: string) {
  return new Date(value).toLocaleString("zh-CN", { hour12: false })
}

export function messageOf(error: unknown) {
  return error instanceof Error ? error.message : "请求失败"
}
