// 全局错误弹窗状态：App.vue 负责 provide，任意组件 inject 后调用 showError 触发弹窗。
// 采用 provide/inject 而非引入状态库（项目当前无 Pinia），轻量且满足全局复用。
import { inject, provide, ref, type Ref } from 'vue'

// 注入/提供的 key：字符串常量，避免模块间重复定义 key 冲突
const ERROR_MODAL_KEY = 'errorModal'

export interface ErrorModalState {
  message: Ref<string>
  title: Ref<string>
  visible: Ref<boolean>
  showError: (msg: string, title?: string) => void
  closeError: () => void
}

// 全局唯一状态实例：模块级单例，App.vue 挂载时提供，任意组件注入同一份
const state = {
  message: ref(''),
  title: ref('出错了'),
  visible: ref(false),
  // 可选 title 参数：兼容既有调用（不传时仍显示默认"出错了"），
  // 供"删除成功"这类非错误提示用有意义的标题
  showError: (msg: string, title?: string) => {
    // 幂等：连续触发只更新文案并确保弹窗可见，不叠加多个弹窗
    state.message.value = msg
    // 每次调用都重置标题：不传则回退默认，避免上次的标题残留
    state.title.value = title ?? '出错了'
    state.visible.value = true
  },
  closeError: () => {
    state.visible.value = false
  },
}

// 供 App.vue 在 setup 中调用：把全局错误状态注入子组件树
export function provideErrorModal() {
  provide(ERROR_MODAL_KEY, state)
}

// 供任意组件调用：读出弹窗状态（App.vue 绑定用）+ 触发/关闭弹窗
export function useErrorModal() {
  const injected = inject<ErrorModalState>(ERROR_MODAL_KEY, state)
  return {
    visible: injected.visible,
    message: injected.message,
    title: injected.title,
    showError: injected.showError,
    closeError: injected.closeError,
  }
}
