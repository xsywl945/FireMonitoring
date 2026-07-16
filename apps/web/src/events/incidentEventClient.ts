import { Client } from '@stomp/stompjs'
import { isMockMode, tokenStorage } from '@/api/client'
import { mockIncidents } from '@/api/mockData'
import type { IncidentSummary } from '@/types/domain'

export type EventConnectionState = 'DISCONNECTED' | 'CONNECTING' | 'CONNECTED' | 'ERROR'
type IncidentHandler = (incident: IncidentSummary) => void
type StateHandler = (state: EventConnectionState) => void

export interface IncidentEventClient {
  connect(): void
  disconnect(): Promise<void>
  onIncident(handler: IncidentHandler): () => void
  onState(handler: StateHandler): () => void
}

export function createIncidentEventClient(): IncidentEventClient {
  const incidentHandlers = new Set<IncidentHandler>()
  const stateHandlers = new Set<StateHandler>()
  let client: Client | undefined
  let mockTimer: number | undefined
  const emitState = (state: EventConnectionState) => stateHandlers.forEach((handler) => handler(state))

  return {
    connect() {
      emitState('CONNECTING')
      if (isMockMode) {
        window.setTimeout(() => emitState('CONNECTED'), 120)
        if (import.meta.env.VITE_MOCK_EVENTS === 'true') {
          mockTimer = window.setInterval(() => {
            const incident = mockIncidents.find((item) => item.status === 'NEW')
            if (incident) incidentHandlers.forEach((handler) => handler(structuredClone(incident)))
          }, 30_000)
        }
        return
      }
      client = new Client({
        brokerURL:
          import.meta.env.VITE_WS_URL ||
          `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/events`,
        connectHeaders: tokenStorage.get() ? { Authorization: `Bearer ${tokenStorage.get()}` } : {},
        reconnectDelay: 3_000,
        heartbeatIncoming: 10_000,
        heartbeatOutgoing: 10_000,
        onConnect: () => {
          emitState('CONNECTED')
          client?.subscribe(import.meta.env.VITE_STOMP_INCIDENT_TOPIC || '/topic/incidents', (message) => {
            try {
              const incident = JSON.parse(message.body) as IncidentSummary
              incidentHandlers.forEach((handler) => handler(incident))
            } catch {
              emitState('ERROR')
            }
          })
        },
        onStompError: () => emitState('ERROR'),
        onWebSocketClose: () => emitState('DISCONNECTED'),
      })
      client.activate()
    },
    async disconnect() {
      if (mockTimer) window.clearInterval(mockTimer)
      if (client) await client.deactivate()
      emitState('DISCONNECTED')
    },
    onIncident(handler) {
      incidentHandlers.add(handler)
      return () => incidentHandlers.delete(handler)
    },
    onState(handler) {
      stateHandlers.add(handler)
      return () => stateHandlers.delete(handler)
    },
  }
}
