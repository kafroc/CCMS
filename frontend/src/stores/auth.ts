import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '@/api/auth'

interface UserInfo {
  id: string
  username: string
  role: string
  must_change_password?: boolean
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('token'))
  const user = ref<UserInfo | null>(
    JSON.parse(localStorage.getItem('user') || 'null')
  )

  const isLoggedIn = computed(() => !!token.value)
  const isAdmin = computed(() => user.value?.role === 'admin')
  const mustChangePassword = computed(() => !!user.value?.must_change_password)

  function persist() {
    if (token.value) localStorage.setItem('token', token.value)
    else localStorage.removeItem('token')
    if (user.value) localStorage.setItem('user', JSON.stringify(user.value))
    else localStorage.removeItem('user')
  }

  async function login(username: string, password: string) {
    const res = await authApi.login(username, password)
    token.value = res.data.access_token
    user.value = res.data.user
    persist()
  }

  function logout() {
    token.value = null
    user.value = null
    persist()
  }

  function clearMustChangePassword() {
    if (user.value) {
      user.value = { ...user.value, must_change_password: false }
      persist()
    }
  }

  return { token, user, isLoggedIn, isAdmin, mustChangePassword, login, logout, clearMustChangePassword }
})
