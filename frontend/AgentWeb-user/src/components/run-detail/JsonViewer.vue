<template>
  <div class="json-viewer">
    <div v-for="(value, key) in data" :key="String(key)" class="json-row">
      <span class="json-key">{{ key }}</span>
      <span class="json-sep">:</span>
      <!-- 值是对象：递归展示缩进子节点 -->
      <JsonViewer
        v-if="isPlainObject(value)"
        :data="value"
        class="json-nested"
      />
      <!-- 值是数组：只显示长度，够用且不撑爆页面 -->
      <span v-else-if="Array.isArray(value)" class="json-value json-array">
        [{{ value.length }} 项]
      </span>
      <!-- 布尔值着色：true 绿 / false 红 -->
      <span v-else-if="typeof value === 'boolean'"
        class="json-value"
        :class="value ? 'json-true' : 'json-false'"
      >{{ value }}</span>
      <!-- 其余值原样显示 -->
      <span v-else class="json-value">{{ value }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
// 递归 JSON 展示：定义组件名以便模板自引用
defineOptions({ name: 'JsonViewer' })

defineProps<{
  data: Record<string, unknown>
}>()

// 判断是否为普通对象（非 null、非数组），决定是否递归
function isPlainObject(val: unknown): val is Record<string, unknown> {
  return typeof val === 'object' && val !== null && !Array.isArray(val)
}
</script>

<style scoped>
/* 等宽字体 + 键名紫色、布尔值着色，与 Apple 风格的低饱和配色一致 */
.json-viewer {
  font-family: 'SF Mono', 'Menlo', monospace;
  font-size: 13px;
  line-height: 1.6;
}

.json-row {
  display: flex;
  gap: 4px;
  align-items: baseline;
  flex-wrap: wrap;
}

.json-key { color: #AF52DE; font-weight: 500; }
.json-sep { color: #8E8E93; }
.json-value { color: #1C1C1E; }
.json-true { color: #34C759; font-weight: 600; }
.json-false { color: #FF3B30; font-weight: 600; }
.json-array { color: #8E8E93; font-style: italic; }

.json-nested {
  padding-left: 16px;
  border-left: 2px solid #E5E5EA;
  margin-left: 4px;
}
</style>