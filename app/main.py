"""FastAPI 应用入口：API + 静态前端（单进程一体部署）。"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.chat import router as chat_router
from app.config import BASE_DIR, get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动预热：提前加载分词词典与知识库索引，避免首个用户请求承担冷启动成本。"""
    from app.knowledge.retriever import get_knowledge_base

    kb = get_knowledge_base()
    logger.info("knowledge base ready: %s docs", kb.size)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)

    # 演示环境放开跨域；生产按域名收敛
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(chat_router)

    @app.get("/api/health")
    async def health() -> dict:
        from app.knowledge.retriever import get_knowledge_base

        return {
            "status": "ok",
            "app": settings.app_name,
            "mode": "mock" if settings.use_mock else "real",
            "model": settings.llm_model,
            "vlm_model": settings.vlm_model,
            "knowledge_docs": get_knowledge_base().size,
        }

    frontend_dir = BASE_DIR / "frontend"
    if frontend_dir.exists():
        app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
    return app


app = create_app()
