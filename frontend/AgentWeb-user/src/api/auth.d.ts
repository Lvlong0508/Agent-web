// auth.js 的类型声明：让 TS 文件（如 main.ts）能安全 import 这个 JS 模块
// 只声明对外导出的函数签名，实现仍在 auth.js 中
export declare function ensureUserId(): Promise<string>
