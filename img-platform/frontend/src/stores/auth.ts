import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '../services/api'

export interface User {
  id: number
  username: string
  is_admin: boolean
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || null)
  const user = ref<User | null>(null)
  const error = ref<string | null>(null)

  const isLoggedIn = computed(() => !!token.value)

  function setToken(newToken: string) {
    token.value = newToken
    localStorage.setItem('token', newToken)
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
    localStorage.removeItem('token')
  }

  // 初始化时恢复登录状态
  if (token.value) {
    fetchMe()
  }

  return { token, user, error, isLoggedIn, login, fetchMe, logout }
})
