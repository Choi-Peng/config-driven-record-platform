"""
应用环境配置。

Version: 1.0.0
负责加载 `.env` 并提供统一的运行时敏感配置读取入口。
"""
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录下的 .env；不覆盖已在环境中的变量（数据库路径见 config/main.yaml data_path.database）
_REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_REPO_ROOT / ".env", override=False)


@lru_cache
def get_settings():
    """从环境读取；生产环境务必设置 ADMIN_PASSWORD 与 SESSION_SECRET。"""
    session_secret = os.environ.get("SESSION_SECRET", "").strip()
    if not session_secret:
        session_secret = "dev-only-insecure-session-secret"

    return {
        "admin_username": os.environ.get("ADMIN_USERNAME", "admin").strip() or "admin",
        "admin_password": os.environ.get("ADMIN_PASSWORD", "").strip(),
        "session_secret": session_secret,
    }
