import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '../auth'

describe('auth store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('persists a successful mock login and clears it on logout', async () => {
    const store = useAuthStore()
    await store.login('admin', '123456')

    expect(store.isAuthenticated).toBe(true)
    expect(store.isAdmin).toBe(true)
    expect(store.user?.displayName).toBe('石旭生')
    expect(localStorage.getItem('fire-monitoring.access-token')).toBeTruthy()

    store.logout()
    expect(store.isAuthenticated).toBe(false)
    expect(localStorage.getItem('fire-monitoring.access-token')).toBeNull()
  })
})
