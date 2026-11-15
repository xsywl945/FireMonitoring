export const sceneLabels: Record<string, string> = {
  classroom: "教室",
  laboratory: "实验室",
  electrical_room: "配电间",
  dormitory: "宿舍",
  kitchen: "食堂后厨",
  warehouse: "仓库",
  corridor: "走廊",
}

export const causeLabels: Record<string, string> = {
  electrical_short: "电气短路",
  open_flame: "明火引燃",
  lab_reagent: "实验试剂",
  cooking_oil: "烹饪油脂",
  smoking: "吸烟",
  unknown: "未知",
}

export const smokeColorLabels: Record<string, string> = {
  none: "无",
  white: "白",
  gray: "灰",
  black: "黑",
  unknown: "未知",
}

export const smokeDensityLabels: Record<string, string> = {
  none: "无",
  light: "淡",
  dense: "浓",
  unknown: "未知",
}

export const growthLabels: Record<string, string> = {
  slow: "慢速",
  medium: "中速",
  fast: "快速",
  ultrafast: "超快速",
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

export const alertStatusLabels: Record<string, string> = {
  OPEN: "待处置",
  ACKNOWLEDGED: "已确认",
  FALSE_ALARM: "误报",
  CLOSED: "已结案",
}

export const dispositionLabels: Record<string, string> = {
  acknowledge: "确认",
  false_alarm: "标记误报",
  close: "结案",
}

export const faultLabels: Record<string, string> = {
  OFFLINE: "离线",
  FROZEN: "画面冻结",
  BLUR: "严重模糊",
}

export function healthText(item: { online: boolean; frozen: boolean; blur: boolean }) {
  if (!item.online) return "离线"
  const marks = ["在线"]
  if (item.frozen) marks.push("画面冻结")
  if (item.blur) marks.push("严重模糊")
  return marks.join("，")
}

export function formatTime(value: string) {
  return new Date(value).toLocaleString("zh-CN", { hour12: false })
}

export function messageOf(error: unknown) {
  return error instanceof Error ? error.message : "请求失败"
}
