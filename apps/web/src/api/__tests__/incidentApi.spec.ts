import { incidentApi } from '../index'

describe('mock incident API', () => {
  it('filters incidents with the contract enums', async () => {
    const incidents = await incidentApi.list({ severity: 'CRITICAL', status: 'NEW' })
    expect(incidents).toHaveLength(1)
    expect(incidents[0]?.primaryType).toBe('FIRE_AND_SMOKE')
  })

  it('uses the allowed transition action names', async () => {
    const detail = await incidentApi.transition(24071600, { action: 'RESOLVE', note: '现场已排除风险' })
    expect(detail.status).toBe('RESOLVED')
    expect(detail.timeline[0]?.note).toBe('现场已排除风险')
  })
})
