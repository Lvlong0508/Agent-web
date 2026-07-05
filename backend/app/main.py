from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.auth import router as auth_router
from app.database import init_db
from app.db.mongodb import MongoDB
from app.exceptions import AppException


# 应用生命周期：启动时自动创建数据库表
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()           # 初始化 MySQL
    await MongoDB.connect()   # 初始化 MongoDB
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
app.include_router(auth_router)
