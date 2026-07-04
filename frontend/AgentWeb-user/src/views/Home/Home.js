import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/store/auth'
import { LOGOUT_CONFIRM } from './Text'

export function useHome() {
  const router = useRouter()
  const authStore = useAuthStore()

  onMounted(() => {
    authStore.init()
  })

  function logout() {
    if (confirm(LOGOUT_CONFIRM)) {
      authStore.clearAuth()
      router.push('/login')
    }
  }

  return { authStore, logout }
}
