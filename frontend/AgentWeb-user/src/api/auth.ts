// 用户身份模块：启动时向后端引导接口索取 user_id，存 localStorage，供请求头使用
// @ts-expect-error index.js 是普通 JS 无类型声明，这里只用到 axios 实例的 get
import http from './index'

// localStorage 键名：缓存当前设备分配到的用户 ID
const USER_ID_KEY = 'agentweb_user_id'

// 获取当前用户 ID：优先取本地缓存，没有则请求引导接口并缓存
export async function ensureUserId(): Promise<string> {
  const cached = localStorage.getItem(USER_ID_KEY)
  if (cached) return cached

  // 泛型标注响应结构：后端返回 { user_id: string }
  const { data } = await http.get<{ user_id: string }>('/auth/guest')
  const uid = data.user_id
  if (uid) {
    localStorage.setItem(USER_ID_KEY, uid)
    return uid
  }
  throw new Error('引导接口未返回 user_id')
}
