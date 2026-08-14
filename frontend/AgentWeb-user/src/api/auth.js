// 用户身份模块：启动时向后端引导接口索取 user_id，存 localStorage，供请求头使用
import http from './index'

// localStorage 键名：缓存当前设备分配到的用户 ID
const USER_ID_KEY = 'agentweb_user_id'

// 获取当前用户 ID：优先取本地缓存，没有则请求引导接口并缓存
export async function ensureUserId() {
  let uid = localStorage.getItem(USER_ID_KEY)
  if (uid) return uid
  const { data } = await http.get('/auth/guest')
  uid = data.user_id
  localStorage.setItem(USER_ID_KEY, uid)
  return uid
}
