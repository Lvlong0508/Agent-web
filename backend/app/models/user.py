from sqlalchemy import Column, Integer, String, DateTime, func
from sqlalchemy.orm import DeclarativeBase


# SQLAlchemy ORM 基类，所有模型继承此类
class Base(DeclarativeBase):
    pass


# 用户表 ORM 模型，对应 MySQL 的 users 表
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), nullable=False, unique=True)   # 用户名，唯一
    email = Column(String(100), nullable=False, unique=True)     # 邮箱，唯一
    hashed_password = Column(String(255), nullable=False)        # bcrypt 哈希后的密码
    created_at = Column(DateTime, server_default=func.now())     # 注册时间
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())  # 更新时间
