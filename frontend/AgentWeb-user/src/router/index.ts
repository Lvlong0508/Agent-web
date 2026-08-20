import { createRouter, createWebHistory } from 'vue-router'

// 路由配置：聊天页 `/` 与运行记录页 `/runs`，登录/注册/个人中心均已移除
const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'chat',
      component: () => import('@/views/Chat/Chat.vue'),
    },
    {
      path: '/runs',
      name: 'runs',
      component: () => import('@/views/Runs/Runs.vue'),
    },
  ],
})

export default router
