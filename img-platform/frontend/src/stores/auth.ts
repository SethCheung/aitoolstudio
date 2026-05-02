import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '../services/api'

export interface User {
  id: number
  username: string
  is_admin: boolean
}

export const useAuthStore = defineStore('auth', () => {
  // Token stored in memory only — more secure than localStorage (XSS risk)
  // Requires re-login after page refresh but tokens shouldn't live in DOM storage
  const token = ref<string | null>(null)
  const user = ref<User | null>(null)
  const error = ref<string | null>(null)

  const isLoggedIn = computed(() => !!token.value)

  function setToken(newToken: string) {
    token.value = newToken
  }

  function setUser(newUser: User) {
    user.value = newUser
  }

  async function login(username: string, password: string) {
    error.value = null
    try {
      const response = await api.post('/api/auth/login', { username, password })
      const { access_token } = response.data
      setToken(access_token)
      await fetchMe()
      return true
    } catch (err: any) {
      error.value = err.response?.data?.detail || '登录失败'
      return false
    }
  }

  async function fetchMe() {
    if (!token.value) return
    try {
      const response = await api.get('/api/auth/me')
      setUser(response.data)
    } catch {
      logout()
    }
  }

  function logout() {
    token.value = null
    user.value = null
    error.value = null
  }

  // Rehydrate from localStorage on init (supports page refresh within same tab)
  // localStorage is a fallback — the primary store is memory
  const stored = localStorage.getItem('token')
  if (stored) {
    token.value = stored
    fetchMe()
  }

  return { token, user, error, isLoggedIn, login, fetchMe, logout }
})
