<template>
  <div class="json-viewer">
    <!-- 数组：逐项编号展示，对象项递归展开（tool 结果的 items 每项明细可读） -->
    <template v-if="isArray">
      <div v-for="(item, idx) in data" :key="idx" class="json-row">
        <span class="json-key">{{ idx }}</span>
        <span class="json-sep">:</span>
        <JsonViewer v-if="isPlainObject(item)" :data="item as Record<string, unknown>" class="json-nested" />
        <!-- 数组元素还是数组：只显示长度，避免无限递归 -->
        <span v-else-if="Array.isArray(item)" class="json-value" :class="'json-array'">[{{ item.length }} 项]</span>
        <span v-else-if="typeof item === 'boolean'" class="json-value" :class="item ? 'json-true' : 'json-false'">{{ item }}</span>
        <span v-else class="json-value">{{ item }}</span>
      </div>
    </template>
    <!-- 对象：键值逐行展示 -->
    <template v-else>
      <div v-for="(value, key) in data as Record<string, unknown>" :key="String(key)" class="json-row">
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
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
// 递归 JSON 展示：定义组件名以便模板自引用
defineOptions({ name: 'JsonViewer' })

const props = defineProps<{
  // 支持对象（键值对）或数组（tool 结果的 items 列表），按顶层类型分两支渲染
  data: Record<string, unknown> | unknown[]
}>()

// 顶层是数组（tool 结果 items 等）与对象用两套渲染分支
const isArray = computed(() => Array.isArray(props.data))

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