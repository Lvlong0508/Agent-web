from contextlib import asynccontextmanager
import logging
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import audit_env
from app.api.v1.chat import router as chat_router
from app.api.v1.auth import router as auth_router
from app.api.v1.agent_runs import router as agent_runs_router
from app.middleware.mongodb import MongoDB
from app.middleware.mysql import Base, engine
from app.middleware.chroma import ChromaClient
from app.services.agent.skills import loader as skills_loader
from app.services.knowledge.embedder import DashScopeEmbedder
from app.services.knowledge.skill_service import SkillKnowledgeService
from app.exceptions import AppException
import app.models.expense  # noqa: F401  导入模型让 Base.metadata 注册 expenses 表

# 日志初始化：默认 INFO 级别输出到控制台，便于排查验证器/标题节点等关键链路
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

# 屏蔽 httpx 的 HTTP 请求日志：每次调用 LLM 都会刷一行
# "HTTP Request: POST https://dashscope..."，纯噪音；只保留 WARNING 及以上的异常日志
logging.getLogger("httpx").setLevel(logging.WARNING)


# 应用生命周期：启动时初始化 MongoDB 并自动创建 MySQL 表
# 技能入库后台任务引用：保留以便 shutdown 时取消，避免与 ChromaClient.close() 竞争
_sync_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _sync_task
    audit_env()               # 扫描 .env 中未被认领的键，配置拼写错误尽早暴露
    await MongoDB.connect()   # 初始化 MongoDB
    ChromaClient.connect()    # 初始化 Chroma 向量库（4 个 collection）
    # 自动建表：expenses 表不存在时创建（含索引），已存在则跳过
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # 技能向量入库：异步后台任务，不阻塞启动（失败仅记日志，检索层降级兜底）
    _sync_task = asyncio.create_task(_sync_skills_to_vector_db())
    yield
    # 关闭前取消未完成的入库任务，避免其仍访问 Chroma 与 close() 竞争
    if _sync_task and not _sync_task.done():
        _sync_task.cancel()
        try:
            await _sync_task
        except (asyncio.CancelledError, Exception):
            pass  # 取消/失败都不影响正常关闭
    await MongoDB.close()     # 关闭 MongoDB
    ChromaClient.close()      # 关闭 Chroma


async def _sync_skills_to_vector_db() -> None:
    """后台把磁盘技能增量同步到向量库（kb_skills）。

    单独函数便于启动时 create_task 调用；任何失败只记日志，
    不抛给 lifespan（入库失败 → 检索降级，主流程不受影响）。
    """
    try:
        service = SkillKnowledgeService(
            ChromaClient.get_collection("skill"),
            DashScopeEmbedder(),
        )
        await service.sync_from_disk(skills_loader)
        logging.getLogger(__name__).info("技能向量库同步完成")
    except Exception as e:
        logging.getLogger(__name__).warning("技能向量库同步失败（检索将降级）：%s", e)


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
app.include_router(agent_runs_router)
