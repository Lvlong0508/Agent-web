<script setup>
import { TITLE, SUBMIT, USERNAME_LABEL, PASSWORD_LABEL, USERNAME_PLACEHOLDER, PASSWORD_PLACEHOLDER, TO_REGISTER } from './Text'
import { useLogin } from './Login'
import './Login.css'

const { username, password, loading, error, handleSubmit, goRegister } = useLogin()
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <h2>{{ TITLE }}</h2>
      <div v-if="error" class="error-msg">{{ error }}</div>
      <form @submit.prevent="handleSubmit">
        <div class="form-group">
          <label>{{ USERNAME_LABEL }}</label>
          <input v-model="username" type="text" :placeholder="USERNAME_PLACEHOLDER" />
        </div>
        <div class="form-group">
          <label>{{ PASSWORD_LABEL }}</label>
          <input v-model="password" type="password" :placeholder="PASSWORD_PLACEHOLDER" />
        </div>
        <button type="submit" class="submit-btn" :disabled="loading">{{ SUBMIT }}</button>
      </form>
      <div class="login-footer">
        <a @click="goRegister">{{ TO_REGISTER }}</a>
      </div>
    </div>
  </div>
</template>
