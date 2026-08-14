<script setup lang="ts">
import { watch, onUnmounted } from 'vue'

// 全局错误弹窗：Apple 风格单按钮确认框。
// Props 由父组件通过 :visible / :message 传入，用户确认后 emit close 事件。
// 点击遮罩或按 Esc 也触发关闭（与确认按钮行为一致）。
const props = defineProps<{
  visible: boolean
  message: string
}>()

const emit = defineEmits<{
  close: []
}>()

// 关闭弹窗：由父组件把 visible 置回 false（避免子组件直接修改 props）
function onClose() {
  emit('close')
}

// Esc 键处理函数：当按下的键是 Escape 时关闭弹窗。
// 单独抽出为具名函数，方便在 watch 与 onUnmounted 中绑定和解绑同一引用。
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    onClose()
  }
}

// 监听 visible 变化：弹窗显示时给 window 绑定 keydown 监听，
// 弹窗隐藏时立即解绑，避免弹窗关闭后按键仍被拦截。
watch(
  () => props.visible,
  (val) => {
    if (val) {
      window.addEventListener('keydown', onKeydown)
    } else {
      window.removeEventListener('keydown', onKeydown)
    }
  }
)

// 组件卸载时移除监听，防止内存泄漏
onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <!-- Teleport 把弹窗挂到 body 下，避免被父级 overflow/transform 裁剪或影响层级 -->
  <Teleport to="body">
    <!-- Transition 控制弹窗显示/隐藏动画；v-if="visible" 保证关闭后从 DOM 移除 -->
    <Transition name="modal-fade">
      <div v-if="visible" class="modal-overlay" @click.self="onClose">
        <!-- role="alertdialog" 让屏幕阅读器把弹窗识别为可打断的对话框 -->
        <div class="modal-card" role="alertdialog" aria-modal="true">
          <h3 class="modal-title">出错了</h3>
          <p class="modal-message">{{ message }}</p>
          <button class="modal-confirm" @click="onClose">知道了</button>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
/* 遮罩：铺满全屏、半透明背景加毛玻璃，层级 1000 保证盖住导航栏与聊天内容 */
.modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.35);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}

/* 卡片：白色圆角卡片，宽度有上限同时适配小屏，居中排版 */
.modal-card {
  width: min(320px, 86vw);
  padding: 24px 20px 18px;
  background: #fff;
  border-radius: 18px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.18);
  text-align: center;
}

/* 标题：Apple 风格深灰加粗小标题 */
.modal-title {
  margin: 0 0 10px;
  font-size: 17px;
  font-weight: 600;
  color: #1d1d1f;
}

/* 消息文本：浅灰、行高舒适，超出两行自然换行 */
.modal-message {
  margin: 0 0 20px;
  font-size: 14px;
  line-height: 1.6;
  color: #86868b;
  word-break: break-word;
}

/* 按钮：占满宽度、胶囊造型，主色蓝底白字，悬停略微提亮 */
.modal-confirm {
  width: 100%;
  height: 36px;
  border: none;
  border-radius: 999px;
  background: #007aff;
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: filter 0.2s ease;
}

.modal-confirm:hover {
  filter: brightness(1.08);
}

/* 淡入淡出：整体透明度过渡 0.2s */
.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.2s ease;
}

.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}

/* 卡片从下方 8px 处上浮进入，营造轻微"弹起"的动效 */
.modal-fade-enter-active .modal-card,
.modal-fade-leave-active .modal-card {
  transition: transform 0.2s ease;
}

.modal-fade-enter-from .modal-card,
.modal-fade-leave-to .modal-card {
  transform: translateY(8px);
}
</style>
