# 自定义异常体系：所有业务异常继承 AppException，由全局处理器统一转为 JSON
# 每个异常携带：detail（用户提示）、code（错误码）、status_code（HTTP 状态码）


class AppException(Exception):
    def __init__(self, detail: str, code: str, status_code: int = 400):
        self.detail = detail
        self.code = code
        self.status_code = status_code


# 409 用户名或邮箱已存在
class UserExistsError(AppException):
    def __init__(self, field: str):
        super().__init__(
            detail=f"{field} already exists",
            code="USER_EXISTS",
            status_code=409,
        )


# 401 用户名或密码错误
class InvalidCredentialsError(AppException):
    def __init__(self):
        super().__init__(
            detail="Invalid username or password",
            code="INVALID_CREDENTIALS",
            status_code=401,
        )


# 401 未认证或 Token 无效
class UnauthorizedError(AppException):
    def __init__(self, detail: str = "Not authenticated"):
        super().__init__(
            detail=detail,
            code="UNAUTHORIZED",
            status_code=401,
        )


# 404 资源不存在
class NotFoundError(AppException):
    def __init__(self, entity: str = "Resource"):
        super().__init__(
            detail=f"{entity} not found",
            code="NOT_FOUND",
            status_code=404,
        )
