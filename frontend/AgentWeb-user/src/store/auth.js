import { defineStore } from 'pinia'
import { register as apiRegister, login as apiLogin, getMe } from '@/api/auth'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null,
  }),
  getters: {
    isAuthenticated: (state) => !!state.user,
  },
  actions: {
    setAuth(accessToken, refreshToken) {
      localStorage.setItem('access_token', accessToken)
      localStorage.setItem('refresh_token', refreshToken)
    },
    clearAuth() {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      this.user = null
    },
    async register(data) {
      const res = await apiRegister(data)
      return res.data
    },
    async login(data) {
      const res = await apiLogin(data)
      this.setAuth(res.data.access_token, res.data.refresh_token)
      await this.fetchUser()
    },
    async fetchUser() {
      const token = localStorage.getItem('access_token')
      if (!token) {
        this.user = null
        return
      }
      try {
        const res = await getMe()
        this.user = res.data
      } catch {
        this.user = null
      }
    },
    async init() {
      const token = localStorage.getItem('access_token')
      if (token) {
        await this.fetchUser()
      }
    },
  },
})
