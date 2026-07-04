<script setup>
import { WELCOME, LOGOUT, USER_INFO, USERNAME, EMAIL, CREATED_AT } from './Text'
import { useHome } from './Home'
import './Home.css'

const { authStore, logout } = useHome()
</script>

<template>
  <div class="home-page">
    <header class="home-header">
      <h1>{{ WELCOME }}{{ authStore.user ? `, ${authStore.user.username}` : '' }}</h1>
      <button class="logout-btn" @click="logout">{{ LOGOUT }}</button>
    </header>
    <div class="home-content">
      <div v-if="!authStore.user" class="loading">加载中...</div>
      <div v-else class="user-card">
        <h2>{{ USER_INFO }}</h2>
        <div class="info-row">
          <span class="info-label">{{ USERNAME }}</span>
          <span class="info-value">{{ authStore.user.username }}</span>
        </div>
        <div class="info-row">
          <span class="info-label">{{ EMAIL }}</span>
          <span class="info-value">{{ authStore.user.email }}</span>
        </div>
        <div class="info-row">
          <span class="info-label">{{ CREATED_AT }}</span>
          <span class="info-value">{{ authStore.user.created_at }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
