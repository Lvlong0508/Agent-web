# 自定义异常体系：所有业务异常继承 AppException，由全局处理器统一转为 JSON
# 每个异常携带：detail（用户提示）、code（错误码）、status_code（HTTP 状态码）


class AppException(Exception):
    def __init__(self, detail: str, code: str, status_code: int = 400):
        self.detail = detail
        self.code = code
        self.status_code = status_code


# 404 资源不存在
class NotFoundError(AppException):
    def __init__(self, entity: str = "Resource"):
        super().__init__(
            detail=f"{entity} not found",
            code="NOT_FOUND",
            status_code=404,
        )
