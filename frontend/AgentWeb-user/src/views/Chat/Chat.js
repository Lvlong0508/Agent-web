import { ref } from 'vue'

export function useChat() {
  const messages = ref([])
  const inputText = ref('')

  function sendMessage() {
    const text = inputText.value.trim()
    if (!text) return
    messages.value.push({ role: 'user', content: text })
    inputText.value = ''
  }

  return { messages, inputText, sendMessage }
}
