import { createRouter, createWebHistory } from 'vue-router'

// 路由配置：目前只保留聊天页 `/` 这一个路由，登录/注册/个人中心均已移除
const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'chat',
      component: () => import('@/views/Chat/Chat.vue'),
    },
  ],
})

export default router
