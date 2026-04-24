"""
应用启动入口。

Version: 1.0.0
负责创建 FastAPI 应用并装配配置、中间件、静态资源与业务路由。
"""
import os

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from app.config import get_settings, get_config_manager
from app.core.config import get_config_service
from app.routers.auth_routes import router as auth_router
from app.routers.entities import router as entities_router
from app.routers.export import router as export_router
from app.routers.pages import router as pages_router
from app.routers.records import router as records_router
from app.routers.options import router as options_router
from app.web import mount_static


def create_app() -> FastAPI:
    # 配置入口由 main.py 显式指定（可通过环境变量覆盖）。
    entry = os.environ.get("APP_CONFIG_ENTRY", "config/main.yaml")
    get_config_manager().set_entry_file(entry)

    main = get_config_service().get_main_config()
    app = FastAPI(title=main.title)

    cfg = get_settings()
    app.add_middleware(
        SessionMiddleware,
        secret_key=cfg["session_secret"],
        session_cookie="ferm_session",
        max_age=14 * 24 * 3600,
        same_site="lax",
    )

    mount_static(app)

    app.include_router(auth_router)
    app.include_router(pages_router)
    app.include_router(entities_router)
    app.include_router(records_router)
    app.include_router(export_router)
    app.include_router(options_router)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    try:
        uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
    except ImportError:
        uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)