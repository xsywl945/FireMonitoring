import { incidentApi } from '../index'

describe('mock incident API', () => {
  it('filters incidents with the contract enums', async () => {
    const incidents = await incidentApi.list({ severity: 'CRITICAL', status: 'NEW' })
    expect(incidents).toHaveLength(1)
    expect(incidents[0]?.primaryType).toBe('FIRE_AND_SMOKE')
  })

})
