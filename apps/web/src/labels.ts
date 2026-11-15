import type { Calibration } from "./api/types"

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

export const healthLabels: Record<string, string> = {
  ok: "正常",
  offline: "离线",
  frozen: "画面冻结",
  blur: "模糊",
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

export function calibrationStatus(calibration: Calibration | null) {
  if (!calibration) return "未标定"
  if (calibration.landmarks.length >= 4) return "已标定"
  return "仅内参"
}

export function px(value: number | null | undefined) {
  if (value == null) return "—"
  return `${value.toFixed(3)} px`
}
