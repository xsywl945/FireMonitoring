import { createIncidentEventClient } from '../incidentEventClient'

describe('incident event client', () => {
  it('reports mock connection state without requiring a backend', async () => {
    vi.useFakeTimers()
    const states: string[] = []
    const client = createIncidentEventClient()
    client.onState((state) => states.push(state))

    client.connect()
    await vi.advanceTimersByTimeAsync(150)
    expect(states).toEqual(['CONNECTING', 'CONNECTED'])

    await client.disconnect()
    expect(states.at(-1)).toBe('DISCONNECTED')
    vi.useRealTimers()
  })
})
