<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <!-- 顶部导航栏：毛玻璃浅色底，悬浮在页面最上层 -->
  <nav class="navbar">
    <div class="navbar-left">
      <span class="navbar-logo" @click="router.push('/')">AgentWeb</span>
    </div>
  </nav>
</template>

<style scoped>
/* Apple 风格导航：半透明毛玻璃 + 细分隔线，与聊天页浅色背景衔接自然 */
.navbar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(20px) saturate(1.8);
  -webkit-backdrop-filter: blur(20px) saturate(1.8);
  border-bottom: 1px solid rgba(0, 0, 0, 0.08);
  z-index: 100;
}

.navbar-logo {
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #007aff;
  cursor: pointer;
  user-select: none;
}
</style>