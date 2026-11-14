import type { LoginResult } from "./types"

const TOKEN = "fire_token"
const ROLE = "fire_role"
const NAME = "fire_name"

export function currentRole() {
  return localStorage.getItem(ROLE)
}

export function currentToken() {
  return localStorage.getItem(TOKEN)
}

export function currentName() {
  return localStorage.getItem(NAME)
}

export function saveSession(result: LoginResult) {
  localStorage.setItem(TOKEN, result.access_token)
  localStorage.setItem(ROLE, result.user.role)
  localStorage.setItem(NAME, result.user.display_name)
}

export function clearSession() {
  localStorage.removeItem(TOKEN)
  localStorage.removeItem(ROLE)
  localStorage.removeItem(NAME)
}

export function signedIn() {
  return Boolean(localStorage.getItem(TOKEN))
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  const token = localStorage.getItem(TOKEN)
  if (token) headers.set("Authorization", `Bearer ${token}`)
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json")
  }
  const response = await fetch(`/api/v1${path}`, { ...init, headers })
  if (response.status === 401) {
    clearSession()
    if (location.pathname !== "/login") location.assign("/login")
    throw new Error("未登录")
  }
  if (!response.ok) {
    const text = await response.text()
    let message = text || response.statusText
    try {
      const body = JSON.parse(text) as { detail?: unknown }
      if (typeof body.detail === "string") message = body.detail
    } catch {
      message = text || response.statusText
    }
    throw new Error(message)
  }
  const type = response.headers.get("content-type") || ""
  if (!type.includes("application/json")) return undefined as T
  return response.json() as Promise<T>
}

export async function fetchBlob(path: string): Promise<string> {
  const headers = new Headers()
  const token = localStorage.getItem(TOKEN)
  if (token) headers.set("Authorization", `Bearer ${token}`)
  const response = await fetch(`/api/v1${path}`, { headers })
  if (!response.ok) throw new Error("读取图片失败")
  return URL.createObjectURL(await response.blob())
}
