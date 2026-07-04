import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/store/auth'
import { LOGIN_SUCCESS, LOGIN_FAILED, INVALID_CREDENTIALS } from './Text'

export function useLogin() {
  const router = useRouter()
  const authStore = useAuthStore()

  const username = ref('')
  const password = ref('')
  const loading = ref(false)
  const error = ref('')

  async function handleSubmit() {
    error.value = ''
    if (!username.value || !password.value) {
      error.value = '请填写用户名和密码'
      return
    }
    loading.value = true
    try {
      await authStore.login({ username: username.value, password: password.value })
      alert(LOGIN_SUCCESS)
      router.push('/')
    } catch (e) {
      const status = e.response?.status
      if (status === 401) {
        error.value = INVALID_CREDENTIALS
      } else {
        error.value = LOGIN_FAILED
      }
    } finally {
      loading.value = false
    }
  }

  function goRegister() {
    router.push('/register')
  }

  return { username, password, loading, error, handleSubmit, goRegister }
}
