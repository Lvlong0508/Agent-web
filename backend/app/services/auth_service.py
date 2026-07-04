from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.user_repository import UserRepository
from app.schemas.auth import UserResponse
from app.exceptions import UserExistsError, InvalidCredentialsError, UnauthorizedError
from app.utils.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)


class AuthService:
    def __init__(self, session: AsyncSession):
        self.dao = UserRepository(session)

    async def register(self, username: str, email: str, password: str) -> UserResponse:
        existing_user = await self.dao.get_by_username(username)
        if existing_user:
            raise UserExistsError("Username")
        existing_email = await self.dao.get_by_email(email)
        if existing_email:
            raise UserExistsError("Email")
        hashed = hash_password(password)
        user = await self.dao.create(username, email, hashed)
        return UserResponse.model_validate(user)

    async def login(self, username: str, password: str) -> dict:
        user = await self.dao.get_by_username(username)
        if not user or not verify_password(password, user.hashed_password):
            raise InvalidCredentialsError()
        return {
            "access_token": create_access_token(user.id),
            "refresh_token": create_refresh_token(user.id),
            "token_type": "bearer",
        }

    async def refresh(self, refresh_token: str) -> dict:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise UnauthorizedError("Invalid refresh token")

        user_id = int(payload["sub"])
        user = await self.dao.get_by_id(user_id)
        if not user:
            raise UnauthorizedError("User not found")

        return {
            "access_token": create_access_token(user.id),
            "refresh_token": create_refresh_token(user.id),
            "token_type": "bearer",
        }

    async def get_current_user(self, user_id: int) -> UserResponse:
        user = await self.dao.get_by_id(user_id)
        if not user:
            raise UnauthorizedError("User not found")
        return UserResponse.model_validate(user)
