<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/store/auth'

const router = useRouter()
const authStore = useAuthStore()

const username = computed(() => authStore.user?.username ?? '')
const avatar = computed(() => username.value.charAt(0).toUpperCase())

function goProfile() {
  router.push('/profile')
}
</script>

<template>
  <nav v-if="authStore.user" class="navbar">
    <div class="navbar-left">
      <span class="navbar-logo" @click="router.push('/')">AgentWeb</span>
    </div>
    <div class="navbar-right">
      <button class="user-btn" @click="goProfile">
        <span class="avatar">{{ avatar }}</span>
        <span class="username">{{ username }}</span>
      </button>
    </div>
  </nav>
</template>

<style scoped>
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
  background: #fff;
  border-bottom: 1px solid #e4e6eb;
  z-index: 100;
}

.navbar-logo {
  font-size: 18px;
  font-weight: 700;
  color: #1a73e8;
  cursor: pointer;
  user-select: none;
}

.navbar-right {
  display: flex;
  align-items: center;
}

.user-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 12px 4px 4px;
  border: none;
  border-radius: 20px;
  background: transparent;
  cursor: pointer;
  transition: background 0.2s;
}

.user-btn:hover {
  background: #f0f2f5;
}

.avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #1a73e8;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
}

.username {
  font-size: 14px;
  color: #333;
  font-weight: 500;
}
</style>
