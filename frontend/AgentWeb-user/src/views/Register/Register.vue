<script setup>
import { TITLE, SUBMIT, USERNAME_LABEL, PASSWORD_LABEL, EMAIL_LABEL, USERNAME_PLACEHOLDER, PASSWORD_PLACEHOLDER, EMAIL_PLACEHOLDER, TO_LOGIN } from './Text'
import { useRegister } from './Register'
import './Register.css'

const { username, email, password, loading, error, handleSubmit, goLogin } = useRegister()
</script>

<template>
  <div class="register-page">
    <div class="register-card">
      <h2>{{ TITLE }}</h2>
      <div v-if="error" class="error-msg">{{ error }}</div>
      <form @submit.prevent="handleSubmit">
        <div class="form-group">
          <label>{{ USERNAME_LABEL }}</label>
          <input v-model="username" type="text" :placeholder="USERNAME_PLACEHOLDER" />
        </div>
        <div class="form-group">
          <label>{{ EMAIL_LABEL }}</label>
          <input v-model="email" type="email" :placeholder="EMAIL_PLACEHOLDER" />
        </div>
        <div class="form-group">
          <label>{{ PASSWORD_LABEL }}</label>
          <input v-model="password" type="password" :placeholder="PASSWORD_PLACEHOLDER" />
        </div>
        <button type="submit" class="submit-btn" :disabled="loading">{{ SUBMIT }}</button>
      </form>
      <div class="register-footer">
        <a @click="goLogin">{{ TO_LOGIN }}</a>
      </div>
    </div>
  </div>
</template>
