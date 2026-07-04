class AppException(Exception):
    def __init__(self, detail: str, code: str, status_code: int = 400):
        self.detail = detail
        self.code = code
        self.status_code = status_code


class UserExistsError(AppException):
    def __init__(self, field: str):
        super().__init__(
            detail=f"{field} already exists",
            code="USER_EXISTS",
            status_code=409,
        )


class InvalidCredentialsError(AppException):
    def __init__(self):
        super().__init__(
            detail="Invalid username or password",
            code="INVALID_CREDENTIALS",
            status_code=401,
        )


class UnauthorizedError(AppException):
    def __init__(self, detail: str = "Not authenticated"):
        super().__init__(
            detail=detail,
            code="UNAUTHORIZED",
            status_code=401,
        )


class NotFoundError(AppException):
    def __init__(self, entity: str = "Resource"):
        super().__init__(
            detail=f"{entity} not found",
            code="NOT_FOUND",
            status_code=404,
        )
