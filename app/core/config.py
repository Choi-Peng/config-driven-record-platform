"""
核心配置服务。

Version: 1.0.0
提供类型化配置访问、缓存控制与统一配置读取入口。
"""
from __future__ import annotations

import os
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass

from .exceptions import ConfigError
from . import get_container, register_service

from app.config.loader import (
    get_main_config,
    get_permission_config,
    get_form_config,
    get_table_config,
    get_active_form_config,
    reload_all_configs,
    get_config_info as _get_config_info
)


@dataclass
class DatabaseConfig:
    """数据库配置"""
    journal_mode: str = "WAL"
    synchronous: str = "NORMAL"
    foreign_keys: bool = True
    busy_timeout: int = 5000
    cache_size: int = -2000
    temp_store: str = "DEFAULT"
    mmap_size: int = 268435456


@dataclass
class DataPaths:
    """数据路径配置"""
    root: str
    database: str
    files: str
    images: str


@dataclass
class FormPageConfig:
    """表单页面配置"""
    title: str
    file: str


@dataclass
class TableConfig:
    """表格配置"""
    title: str
    file: str


@dataclass
class MainConfig:
    """主配置"""
    version: str
    title: str
    image_name_format: str
    data_paths: DataPaths
    database_config: DatabaseConfig
    form_pages: Dict[str, FormPageConfig]
    active_form: str
    tables: Dict[str, TableConfig]


class ConfigService:
    """配置服务"""

    def __init__(self):
        self._main_config: Optional[MainConfig] = None
        self._permission_config: Optional[Dict[str, Any]] = None
        self._form_configs: Dict[str, Dict[str, Any]] = {}
        self._table_configs: Dict[str, Dict[str, Any]] = {}
        self._last_reload_time: float = 0
        self._cache_ttl: int = 300  # 5分钟

    def _load_main_config(self) -> MainConfig:
        """加载主配置"""
        try:
            raw_config = get_main_config()

            # 解析数据路径
            data_paths = DataPaths(
                root=raw_config["data_paths"]["root"],
                database=raw_config["data_paths"]["database"],
                files=raw_config["data_paths"]["files"],
                images=raw_config["data_paths"]["images"]
            )

            # 解析数据库配置
            db_config = DatabaseConfig(
                journal_mode=raw_config["database_config"]["journal_mode"],
                synchronous=raw_config["database_config"]["synchronous"],
                foreign_keys=raw_config["database_config"]["foreign_keys"],
                busy_timeout=raw_config["database_config"]["busy_timeout"],
                cache_size=raw_config["database_config"]["cache_size"]
            )

            # 解析表单页面
            form_pages = {}
            for key, value in raw_config["form_pages"].items():
                form_pages[key] = FormPageConfig(
                    title=value["title"],
                    file=value["file"]
                )

            # 解析表格
            tables = {}
            for key, value in raw_config["tables"].items():
                tables[key] = TableConfig(
                    title=value["title"],
                    file=value["file"]
                )

            return MainConfig(
                version=raw_config["version"],
                title=raw_config["title"],
                image_name_format=str(raw_config.get("image_name_format", "")),
                data_paths=data_paths,
                database_config=db_config,
                form_pages=form_pages,
                active_form=raw_config["active_form"],
                tables=tables,
            )

        except Exception as e:
            raise ConfigError(f"加载主配置失败: {e}", details={"raw_config": raw_config if 'raw_config' in locals() else None})

    def get_main_config(self, force_reload: bool = False) -> MainConfig:
        """获取主配置"""
        if self._main_config is None or force_reload or self._should_reload():
            self._main_config = self._load_main_config()
            self._last_reload_time = time.time()
        return self._main_config

    def get_permission_config(self, force_reload: bool = False) -> Dict[str, Any]:
        """获取权限配置"""
        if self._permission_config is None or force_reload or self._should_reload():
            try:
                self._permission_config = get_permission_config()
            except Exception as e:
                raise ConfigError(f"加载权限配置失败: {e}")
        return self._permission_config

    def get_form_config(self, form_name: str, force_reload: bool = False) -> Dict[str, Any]:
        """获取表单配置"""
        if form_name not in self._form_configs or force_reload or self._should_reload():
            try:
                self._form_configs[form_name] = get_form_config(form_name)
            except Exception as e:
                raise ConfigError(f"加载表单配置失败: {form_name}", details={"form_name": form_name})
        return self._form_configs[form_name]

    def get_table_config(self, table_name: str, force_reload: bool = False) -> Dict[str, Any]:
        """获取表格配置"""
        if table_name not in self._table_configs or force_reload or self._should_reload():
            try:
                self._table_configs[table_name] = get_table_config(table_name)
            except Exception as e:
                raise ConfigError(f"加载表格配置失败: {table_name}", details={"table_name": table_name})
        return self._table_configs[table_name]

    def get_active_form_config(self, force_reload: bool = False) -> Dict[str, Any]:
        """获取活动表单配置"""
        main_config = self.get_main_config(force_reload)
        return self.get_form_config(main_config.active_form, force_reload)

    def get_all_form_configs(self, force_reload: bool = False) -> Dict[str, Dict[str, Any]]:
        """获取所有表单配置"""
        main_config = self.get_main_config(force_reload)
        result = {}
        for form_name in main_config.form_pages.keys():
            result[form_name] = self.get_form_config(form_name, force_reload)
        return result

    def get_all_table_configs(self, force_reload: bool = False) -> Dict[str, Dict[str, Any]]:
        """获取所有表格配置"""
        main_config = self.get_main_config(force_reload)
        result = {}
        for table_name in main_config.tables.keys():
            result[table_name] = self.get_table_config(table_name, force_reload)
        return result

    def reload_all(self):
        """重新加载所有配置"""
        reload_all_configs()
        self._main_config = None
        self._permission_config = None
        self._form_configs.clear()
        self._table_configs.clear()
        self._last_reload_time = time.time()

    def set_cache_ttl(self, ttl: int):
        """设置缓存TTL（秒）"""
        self._cache_ttl = ttl

    def _should_reload(self) -> bool:
        """检查是否应该重新加载"""
        if self._cache_ttl <= 0:
            return True
        return time.time() - self._last_reload_time > self._cache_ttl

    def get_config_info(self) -> Dict[str, Any]:
        """获取配置信息"""
        try:
            info = _get_config_info()
            info.update({
                "cache_ttl": self._cache_ttl,
                "last_reload_time": self._last_reload_time,
                "form_configs_cached": len(self._form_configs),
                "table_configs_cached": len(self._table_configs),
            })
            return info
        except Exception as e:
            raise ConfigError(f"获取配置信息失败: {e}")

    # 便捷属性访问
    @property
    def title(self) -> str:
        """系统标题"""
        return self.get_main_config().title

    @property
    def version(self) -> str:
        """系统版本"""
        return self.get_main_config().version

    @property
    def data_paths(self) -> DataPaths:
        """数据路径"""
        return self.get_main_config().data_paths

    @property
    def database_config(self) -> DatabaseConfig:
        """数据库配置"""
        return self.get_main_config().database_config

    @property
    def active_form(self) -> str:
        """活动表单"""
        return self.get_main_config().active_form

# 创建并注册配置服务
def create_config_service() -> ConfigService:
    """创建配置服务"""
    return ConfigService()


# 注册到服务容器
config_service = create_config_service()
register_service("config", config_service)


# 便捷函数
def get_config_service() -> ConfigService:
    """获取配置服务"""
    return get_container().get("config")


def get_main_config_service() -> MainConfig:
    """获取主配置（便捷函数）"""
    return get_config_service().get_main_config()


def get_permission_config_service() -> Dict[str, Any]:
    """获取权限配置（便捷函数）"""
    return get_config_service().get_permission_config()


def get_form_config_service(form_name: str) -> Dict[str, Any]:
    """获取表单配置（便捷函数）"""
    return get_config_service().get_form_config(form_name)


def get_table_config_service(table_name: str) -> Dict[str, Any]:
    """获取表格配置（便捷函数）"""
    return get_config_service().get_table_config(table_name)


if __name__ == "__main__":
    # 测试配置服务
    service = get_config_service()

    print("配置服务测试:")
    print(f"系统标题: {service.title}")
    print(f"系统版本: {service.version}")
    print(f"活动表单: {service.active_form}")

    print("\n数据库配置:")
    db_config = service.database_config
    print(f"  journal_mode: {db_config.journal_mode}")
    print(f"  synchronous: {db_config.synchronous}")
    print(f"  foreign_keys: {db_config.foreign_keys}")

    print("\n数据路径:")
    paths = service.data_paths
    print(f"  database: {paths.database}")
    print(f"  images: {paths.images}")

    print("\n配置信息:")
    info = service.get_config_info()
    for key, value in info.items():
        print(f"  {key}: {value}")