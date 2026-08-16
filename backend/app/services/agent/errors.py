"""注册阶段统一异常：所有能力注册错误（字段冲突/节点缺失/必需能力失败/工具重名）
都抛本异常，携带能力名与明确原因，由启动入口统一捕获并打印清晰错误（规格 6.3）"""


class CapabilityRegistryError(RuntimeError):
    """能力注册错误：携带出问题的能力名，便于定位"""

    def __init__(self, capability: str, message: str):
        self.capability = capability
        super().__init__(f"[能力 {capability}] {message}")
