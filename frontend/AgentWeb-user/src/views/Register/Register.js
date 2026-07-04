import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/store/auth'
import { REGISTER_SUCCESS, REGISTER_FAILED, USER_EXISTS } from './Text'

export function useRegister() {
  const router = useRouter()
  const authStore = useAuthStore()

  const username = ref('')
  const email = ref('')
  const password = ref('')
  const loading = ref(false)
  const error = ref('')

  async function handleSubmit() {
    error.value = ''
    if (!username.value || !email.value || !password.value) {
      error.value = '请填写所有字段'
      return
    }
    loading.value = true
    try {
      await authStore.register({ username: username.value, password: password.value, email: email.value })
      alert(REGISTER_SUCCESS)
      router.push('/login')
    } catch (e) {
      const status = e.response?.status
      if (status === 409) {
        error.value = USER_EXISTS
      } else {
        error.value = REGISTER_FAILED
      }
    } finally {
      loading.value = false
    }
  }

  function goLogin() {
    router.push('/login')
  }

  return { username, email, password, loading, error, handleSubmit, goLogin }
}
