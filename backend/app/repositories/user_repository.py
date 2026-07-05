import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


# 数据访问层（DAO）：封装用户表的所有数据库操作
class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # 创建新用户
    async def create(self, username: str, email: str, hashed_password: str) -> User:
        user = User(
            id=str(uuid.uuid4()),
            username=username,
            email=email,
            hashed_password=hashed_password,
        )
        self.session.add(user)
        await self.session.flush()     # 刷新到数据库以获取 ID
        await self.session.refresh(user)  # 重新加载最新数据
        return user

    # 根据 ID 查询
    async def get_by_id(self, user_id: str) -> User | None:
        return await self.session.get(User, user_id)

    # 根据用户名查询（用于注册查重、登录验证）
    async def get_by_username(self, username: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()

    # 根据邮箱查询（用于注册查重）
    async def exists_by_email(self, email: str) -> bool:
        result = await self.session.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none() is not None
