import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { ensureUserId } from './api/auth'
import './styles/main.css'

// 启动时先向后端索取 user_id 并缓存，保证后续请求都能带上身份头。
// 失败不阻塞挂载（后端未启动时页面仍可渲染，请求时再报错）
ensureUserId().catch(() => {})

const app = createApp(App)
app.use(router)
app.mount('#app')
