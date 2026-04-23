#!/usr/bin/env python3
"""Project initialization entrypoint.

Run this file manually when you need to initialize/reset database schema:
    python init.py
"""

from pathlib import Path
import os

from app.config import get_config_manager
from app.core.config import get_config_service
from app.db import init_db


def _remove_sqlite_files(db_path: Path) -> None:
    """Remove main DB and SQLite sidecar files (-wal, -shm)."""
    names = [db_path.name, f"{db_path.name}-wal", f"{db_path.name}-shm"]
    for name in names:
        p = db_path.parent / name
        if p.exists():
            p.unlink()


def main() -> None:
    print("🔧 初始化开始...")
    entry = os.environ.get("APP_CONFIG_ENTRY", "config-example/main.yaml")
    get_config_manager().set_entry_file(entry)
    db_path = Path(get_config_service().get_main_config().data_paths.database)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        try:
            _remove_sqlite_files(db_path)
        except PermissionError as e:
            print(
                "❌ 无法删除数据库文件（权限被拒绝）。常见原因：\n"
                "   • 请先停止正在使用数据库的进程（例如运行中的 ./start.sh / uvicorn）。\n"
                "   • 关闭用 SQLite 打开该文件的图形工具（DB Browser 等）。\n"
                f"   文件路径: {db_path}\n"
            )
            raise SystemExit(1) from e
        except OSError as e:
            print(f"❌ 删除数据库文件失败: {e}\n   路径: {db_path}")
            raise SystemExit(1) from e
    init_db()
    print("✅ 初始化完成")


if __name__ == "__main__":
    main()
