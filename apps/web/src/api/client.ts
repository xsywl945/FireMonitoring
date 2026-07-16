import axios, { AxiosError } from 'axios'

const TOKEN_KEY = 'fire-monitoring.access-token'

export const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 12_000,
  headers: { 'Content-Type': 'application/json' },
})

http.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

http.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401 && !window.location.pathname.startsWith('/login')) {
      localStorage.removeItem(TOKEN_KEY)
      window.location.assign(`/login?redirect=${encodeURIComponent(window.location.pathname)}`)
    }
    return Promise.reject(error)
  },
)

export const tokenStorage = {
  key: TOKEN_KEY,
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (token: string) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

export const isMockMode = import.meta.env.VITE_USE_MOCKS !== 'false'
