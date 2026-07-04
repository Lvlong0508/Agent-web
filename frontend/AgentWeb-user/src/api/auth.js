import http from './index'

export function register(data) {
  return http.post('/auth/register', data)
}

export function login(data) {
  return http.post('/auth/login', data)
}

export function refresh(data) {
  return http.post('/auth/refresh', data)
}

export function getMe() {
  return http.get('/auth/me')
}
