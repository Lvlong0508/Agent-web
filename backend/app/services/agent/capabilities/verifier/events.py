"""verifier 能力的事件类型常量：供能力内部 emit 与外部订阅引用，避免散落的字符串"""

VERIFIER_VERDICT_EVENT = "verifier.verdict"  # 质检判定完成（payload.result: pass/retry/fail）
