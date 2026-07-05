<script setup>
import { computed } from 'vue'
import { TITLE, USERNAME, EMAIL, CREATED_AT, BACK, LOGOUT } from './Text'
import { useProfile } from './Profile'
import './Profile.css'

const { authStore, goBack, logout } = useProfile()

const avatar = computed(() => (authStore.user?.username ?? '?').charAt(0).toUpperCase())
</script>

<template>
  <div class="profile-page">
    <div class="profile-card">
      <div class="profile-header">
        <div class="profile-avatar">{{ avatar }}</div>
        <div class="profile-title">
          <h2>{{ TITLE }}</h2>
          <p>{{ authStore.user?.username }}</p>
        </div>
      </div>

      <div class="info-row">
        <span class="info-label">{{ USERNAME }}</span>
        <span class="info-value">{{ authStore.user?.username }}</span>
      </div>
      <div class="info-row">
        <span class="info-label">{{ EMAIL }}</span>
        <span class="info-value">{{ authStore.user?.email }}</span>
      </div>
      <div class="info-row">
        <span class="info-label">{{ CREATED_AT }}</span>
        <span class="info-value">{{ authStore.user?.created_at }}</span>
      </div>

      <div class="profile-actions">
        <button class="btn-back" @click="goBack">{{ BACK }}</button>
        <button class="btn-logout" @click="logout">{{ LOGOUT }}</button>
      </div>
    </div>
  </div>
</template>
