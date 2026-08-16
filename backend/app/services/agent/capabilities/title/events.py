"""title 能力的事件类型常量：供能力内部 emit 与外部订阅引用，避免散落的字符串"""

TITLE_COMPLETED_EVENT = "title.completed"  # 标题生成完成（payload.title: 新标题，可能为空）
