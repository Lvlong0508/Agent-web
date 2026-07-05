import { useRouter } from 'vue-router'
import { useAuthStore } from '@/store/auth'
import { LOGOUT_CONFIRM } from './Text'

export function useProfile() {
  const router = useRouter()
  const authStore = useAuthStore()

  function goBack() {
    router.push('/')
  }

  function logout() {
    if (confirm(LOGOUT_CONFIRM)) {
      authStore.clearAuth()
      router.push('/login')
    }
  }

  return { authStore, goBack, logout }
}
