from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.chat import router as chat_router
from app.api.v1.auth import router as auth_router
from app.middleware.mongodb import MongoDB
from app.middleware.mysql import Base, engine
from app.exceptions import AppException
import app.models.expense  # noqa: F401  导入模型让 Base.metadata 注册 expenses 表

# 日志初始化：默认 INFO 级别输出到控制台，便于排查验证器/标题节点等关键链路
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

# 屏蔽 httpx 的 HTTP 请求日志：每次调用 LLM 都会刷一行
# "HTTP Request: POST https://dashscope..."，纯噪音；只保留 WARNING 及以上的异常日志
logging.getLogger("httpx").setLevel(logging.WARNING)


# 应用生命周期：启动时初始化 MongoDB 并自动创建 MySQL 表
@asynccontextmanager
async def lifespan(app: FastAPI):
    await MongoDB.connect()   # 初始化 MongoDB
    # 自动建表：expenses 表不存在时创建（含索引），已存在则跳过
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await MongoDB.close()     # 关闭 MongoDB


# FastAPI 应用实例
app = FastAPI(title="Agent Web API", version="0.1.0", lifespan=lifespan)

# 跨域配置（开发阶段允许所有来源）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 全局异常处理器：将自定义异常转为统一 JSON 格式返回
@app.exception_handler(AppException)
async def app_exception_handler(request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": exc.code},
    )


# 注册路由模块
app.include_router(chat_router)
app.include_router(auth_router)
