import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { authApi } from '@/api'
import { tokenStorage } from '@/api/client'
import type { User } from '@/types/domain'

const USER_KEY = 'fire-monitoring.user'

function readUser(): User | null {
  try {
    const value = localStorage.getItem(USER_KEY)
    return value ? (JSON.parse(value) as User) : null
  } catch {
    return null
  }
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref(tokenStorage.get())
  const user = ref<User | null>(readUser())
  const loading = ref(false)
  const isAuthenticated = computed(() => Boolean(token.value))
  const isAdmin = computed(() => user.value?.roles.includes('ADMIN') ?? false)

  async function login(username: string, password: string) {
    loading.value = true
    try {
      const response = await authApi.login(username, password)
      token.value = response.accessToken
      user.value = response.user
      tokenStorage.set(response.accessToken)
      localStorage.setItem(USER_KEY, JSON.stringify(response.user))
    } finally {
      loading.value = false
    }
  }

  async function restore() {
    if (!token.value || user.value) return
    try {
      user.value = await authApi.me()
      localStorage.setItem(USER_KEY, JSON.stringify(user.value))
    } catch {
      logout()
    }
  }

  function logout() {
    token.value = null
    user.value = null
    tokenStorage.clear()
    localStorage.removeItem(USER_KEY)
  }

  return { token, user, loading, isAuthenticated, isAdmin, login, restore, logout }
})
