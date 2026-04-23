"""
主配置加载器

加载和管理主配置文件 (config/main.yaml)
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Any
from . import get_config_manager


class MainConfigLoader:
    """主配置加载器"""

    def __init__(self):
        self.config_manager = get_config_manager()
        self._default_config_path = self.config_manager.get_entry_file()

    def _load_data_paths(self, data: dict) -> dict:
        """加载数据路径配置"""
        data_paths = data.get("data_path") if isinstance(data.get("data_path"), dict) else {}
        if not data_paths:
            raise ValueError("data_path is required")

        return {
            "root": str(self.config_manager._abs_path(data_paths.get("root", "data"))),
            "database": str(self.config_manager._abs_path(data_paths.get("database", "data/database/data.db"))),
            "files": str(self.config_manager._abs_path(data_paths.get("files", "data/files"))),
            "images": str(self.config_manager._abs_path(data_paths.get("images", "data/images"))),
        }

    def _load_database_config(self, data: dict) -> dict:
        """加载数据库配置"""
        db_cfg_raw = data.get("database") if isinstance(data.get("database"), dict) else {}
        return {
            "journal_mode": str(db_cfg_raw.get("journal_mode", "WAL")).strip().upper(),
            "synchronous": str(db_cfg_raw.get("synchronous", "NORMAL")).strip().upper(),
            "foreign_keys": bool(db_cfg_raw.get("foreign_keys", True)),
            "busy_timeout": int(db_cfg_raw.get("busy_timeout", 5000)),
            "cache_size": int(db_cfg_raw.get("cache_size", -2000)),
        }

    def _load_form_pages(self, data: dict) -> dict:
        """加载表单页面配置"""
        form_pages = data.get("form_pages") if isinstance(data.get("form_pages"), dict) else {}
        if not form_pages:
            raise ValueError("form_pages is required")

        form_pages_data = {}
        for page_key, page_data in form_pages.items():
            if not isinstance(page_data, dict):
                continue

            raw_form_path = page_data.get("file") or f"forms/{page_key}.yaml"
            form_file = str(self.config_manager.resolve_config_file(raw_form_path)).strip()

            title = str(page_data.get("title", page_key)).strip()

            if self.config_manager._check_file_exists(form_file):
                form_pages_data[page_key] = {
                    "title": title or page_key,
                    "file": form_file,
                }
            else:
                raise ValueError(f"form file {form_file} not found")

        return form_pages_data

    def _load_tables(self, data: dict) -> dict:
        """加载表格配置"""
        tables = data.get("tables") if isinstance(data.get("tables"), dict) else {}
        if not tables:
            raise ValueError("tables is required")

        tables_data = {}
        for table_key, table_data in tables.items():
            if not isinstance(table_data, dict):
                continue

            raw_table_path = table_data.get("file") or f"tables/{table_key}.yaml"
            table_file = str(self.config_manager.resolve_config_file(raw_table_path)).strip()

            title = str(table_data.get("title", table_key)).strip()

            if self.config_manager._check_file_exists(table_file):
                tables_data[table_key] = {
                    "title": title or table_key,
                    "file": table_file,
                }
            else:
                raise ValueError(f"table file {table_file} not found")

        return tables_data


    def load(self, path: str | Path = None) -> Dict[str, Any]:
        """
        加载主配置

        Args:
            path: 配置文件路径，默认为 config/main.yaml

        Returns:
            dict: 主配置数据
        """
        if path is None:
            path = self.config_manager.get_entry_file()
        else:
            path_obj = Path(path)
            if path_obj.is_absolute():
                path = path_obj.resolve()
            else:
                path = self.config_manager.resolve_config_file(str(path_obj))

        # 检查缓存
        cache_key = self.config_manager._get_cache_key("main")
        if self.config_manager._is_cache_valid(cache_key, str(path)):
            return self.config_manager._config_cache[cache_key]

        # 读取配置文件
        data = self.config_manager._read_yaml(path)

        # 加载各个部分
        data_paths = self._load_data_paths(data)
        database_config = self._load_database_config(data)
        form_pages_data = self._load_form_pages(data)

        # 确定活动表单
        active_form = str(data.get("active_form", "")).strip()
        if not active_form or active_form not in form_pages_data:
            active_form = next(iter(form_pages_data.keys()), "")

        tables_data = self._load_tables(data)

        # 构建结果
        result = {
            "version": data.get("version", ""),
            "title": data.get("title", ""),
            "image_name_format": str(data.get("image_name_format", "")).strip(),
            "data_paths": data_paths,
            "database_config": database_config,
            "form_pages": form_pages_data,
            "active_form": active_form,
            "tables": tables_data,
            "users": tables_data.get("users", {}),
            "roles": tables_data.get("roles", {}),
            "permission_system": tables_data.get("permissions", {}),
        }

        # 更新缓存
        self.config_manager._update_cache(cache_key, str(path), result)

        return result


# 全局主配置加载器实例
_main_config_loader: MainConfigLoader = None


def get_main_config_loader() -> MainConfigLoader:
    """获取主配置加载器实例"""
    global _main_config_loader
    if _main_config_loader is None:
        _main_config_loader = MainConfigLoader()
    return _main_config_loader


def load_main_config(path: str | Path = None) -> Dict[str, Any]:
    """加载主配置（便捷函数）"""
    loader = get_main_config_loader()
    return loader.load(path)


if __name__ == "__main__":
    import json

    # 测试主配置加载
    config = load_main_config()
    print(json.dumps(config, ensure_ascii=False, indent=2))

    # 测试缓存
    print("\n缓存信息:")
    print(json.dumps(get_config_manager().get_cache_info(), ensure_ascii=False, indent=2))