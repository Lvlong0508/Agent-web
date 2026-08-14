import axios, { type AxiosInstance } from 'axios'

const http: AxiosInstance = axios.create({
  baseURL: 'http://localhost:8000',
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' },
})

// 请求拦截器：每个 axios 请求发出前执行，自动附带用户 ID 头，后端据此做数据隔离
http.interceptors.request.use((config) => {
  const uid = localStorage.getItem('agentweb_user_id')
  if (uid) config.headers['X-User-Id'] = uid
  return config
})

export default http
