/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_USE_MOCKS?: string
  readonly VITE_MOCK_EVENTS?: string
  readonly VITE_API_BASE_URL?: string
  readonly VITE_WS_URL?: string
  readonly VITE_STOMP_INCIDENT_TOPIC?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
