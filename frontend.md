# 前端代码规格说明

## 目录结构

```
src/
├── api/          # 接口请求
├── assets/       # 静态资源
├── components/   # 通用组件
├── composables/  # 组合式函数（hooks）
├── layout/       # 布局组件
├── router/       # 路由
├── store/        # Pinia 状态
├── styles/       # 全局样式
├── utils/        # 工具函数
├── views/        # 页面
├── App.vue
└── main.js
```

## 页面编写规则

将 `FileName.vue` 拆分成四个文件存入 `FileName` 文件夹：

| 文件 | 职责 |
|------|------|
| `FileName.vue` | 渲染层，负责编写组件等 |
| `FileName.js` | 逻辑层，负责编写算法和请求等 |
| `FileName.css` | 样式层，负责渲染层的样式代码 |
| `Text.js` | 文本层，渲染层和逻辑层需要用到的文本全部写到此文件进行引用 |
