"""planner 能力的事件类型常量：供能力内部 emit 与外部订阅引用，避免散落的字符串"""

PLANNER_COMPLETED_EVENT = "planner.completed"  # 规划完成（payload: status/intent_l1/confidence/cost_time_ms）
PLANNER_FAILED_EVENT = "planner.failed"        # 规划失败/降级（payload: status/reason/cost_time_ms）