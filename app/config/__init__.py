"""
配置管理模块。

Version: 1.0.0
提供统一配置管理入口，支持缓存、热重载与运行时环境设置读取。
"""
from __future__ import annotations

import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Optional, Dict, Any
try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs):
        return False

class ConfigManager:
    """配置管理器（单例）"""

    _instance: Optional[ConfigManager] = None
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._initialized = True
            self._repo_root = Path(__file__).resolve().parent.parent.parent
            self._entry_file: Optional[Path] = None
            self._config_cache: Dict[str, Dict[str, Any]] = {}
            self._config_timestamps: Dict[str, float] = {}
            self._config_files: Dict[str, str] = {}
            self._hot_reload_enabled = True
            self._cache_ttl = 300  # 5分钟

    def get_active_config_root(self) -> Path:
        """当前生效的配置目录（由配置入口文件决定）。"""
        if self._entry_file is not None:
            return self._entry_file.parent
        return (self._repo_root / "config").resolve()

    def set_entry_file(self, entry_file: str | Path) -> Path:
        """设置主配置入口文件，例如 config-example/main.yaml。"""
        path_obj = Path(entry_file)
        if not path_obj.is_absolute():
            path_obj = (self._repo_root / path_obj).resolve()
        else:
            path_obj = path_obj.resolve()
        self._entry_file = path_obj
        return path_obj

    def get_entry_file(self) -> Path:
        """获取主配置入口文件路径。"""
        if self._entry_file is not None:
            return self._entry_file
        return (self._repo_root / "config/main.yaml").resolve()

    def resolve_config_file(self, relative_path: str) -> Path:
        """Resolve config file path against active config root.

        Keeps backward compatibility with legacy "config/..." paths in main.yaml.
        """
        rel = str(relative_path).strip().replace("\\", "/")
        if not rel:
            raise ValueError("empty config path")
        if rel.startswith("config/"):
            rel = rel[len("config/") :]
        elif rel.startswith("config-example/"):
            rel = rel[len("config-example/") :]
        elif rel.startswith("config-template/"):
            rel = rel[len("config-template/") :]
        return (self.get_active_config_root() / rel).resolve()

    def _abs_path(self, path: str | Path) -> Path:
        """获取绝对路径"""
        path_obj = Path(path)
        if path_obj.is_absolute():
            return path_obj.resolve()
        return (self._repo_root / path).resolve()

    def _check_file_exists(self, file_path: str | Path) -> bool:
        """检查文件是否存在"""
        return Path(file_path).exists()

    def _read_yaml(self, file_path: str | Path) -> dict:
        """读取YAML文件"""
        try:
            from app.tools.yaml_parser import YamlParser
            return YamlParser().parse(Path(file_path).resolve())
        except Exception as e:
            raise RuntimeError(f"读取YAML文件失败: {file_path} - {e}")

    def _get_cache_key(self, config_type: str, config_name: str = "") -> str:
        """生成缓存键"""
        return f"{config_type}:{config_name}" if config_name else config_type

    def _is_cache_valid(self, cache_key: str, file_path: str) -> bool:
        """检查缓存是否有效"""
        if cache_key not in self._config_cache:
            return False

        if not self._hot_reload_enabled:
            return True

        # 检查文件是否被修改
        if not self._check_file_exists(file_path):
            return False

        file_mtime = os.path.getmtime(file_path)
        cache_time = self._config_timestamps.get(cache_key, 0)

        # 检查是否过期
        if time.time() - cache_time > self._cache_ttl:
            return False

        return file_mtime <= cache_time

    def _update_cache(self, cache_key: str, file_path: str, data: dict):
        """更新缓存"""
        self._config_cache[cache_key] = data
        self._config_timestamps[cache_key] = time.time()
        self._config_files[cache_key] = file_path

    def clear_cache(self, config_type: str = "", config_name: str = ""):
        """清空缓存"""
        if config_type:
            cache_key = self._get_cache_key(config_type, config_name)
            if cache_key in self._config_cache:
                del self._config_cache[cache_key]
            if cache_key in self._config_timestamps:
                del self._config_timestamps[cache_key]
            if cache_key in self._config_files:
                del self._config_files[cache_key]
        else:
            self._config_cache.clear()
            self._config_timestamps.clear()
            self._config_files.clear()

    def enable_hot_reload(self, enabled: bool = True):
        """启用/禁用热重载"""
        self._hot_reload_enabled = enabled

    def set_cache_ttl(self, ttl: int):
        """设置缓存TTL（秒）"""
        self._cache_ttl = ttl

    def get_cache_info(self) -> Dict[str, Any]:
        """获取缓存信息"""
        return {
            "cache_size": len(self._config_cache),
            "hot_reload_enabled": self._hot_reload_enabled,
            "cache_ttl": self._cache_ttl,
            "cached_configs": list(self._config_cache.keys()),
        }


# 全局配置管理器实例
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """获取配置管理器实例"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_REPO_ROOT / ".env", override=False)


@lru_cache
def get_settings() -> Dict[str, str]:
    """从环境变量加载运行时设置。"""
    session_secret = os.environ.get("SESSION_SECRET", "").strip()
    if not session_secret:
        session_secret = "dev-only-insecure-session-secret"
    return {
        "admin_username": os.environ.get("ADMIN_USERNAME", "admin").strip() or "admin",
        "admin_password": os.environ.get("ADMIN_PASSWORD", "").strip(),
        "session_secret": session_secret,
    }