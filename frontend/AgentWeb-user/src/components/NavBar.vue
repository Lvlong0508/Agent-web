<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <nav class="navbar">
    <div class="navbar-left">
      <span class="navbar-logo" @click="router.push('/')">AgentWeb</span>
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
</style>
