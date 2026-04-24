"""
统一配置加载器。

Version: 1.0.0
提供主配置、表单配置、表格配置与权限配置的统一读取与重载入口。
"""
from __future__ import annotations

from typing import Dict, Any, Optional
from . import get_config_manager
from .main_config import load_main_config
from .form_config import load_form_config_by_name
from .table_config import load_table_config_by_name
from .permission_config import load_permission_config


class ConfigLoader:
    """统一配置加载器"""

    def __init__(self):
        self.config_manager = get_config_manager()
        self._main_config: Optional[Dict[str, Any]] = None
        self._permission_config: Optional[Dict[str, Any]] = None

    def get_main_config(self, reload: bool = False) -> Dict[str, Any]:
        """获取主配置"""
        if self._main_config is None or reload:
            self._main_config = load_main_config()
        return self._main_config

    def get_permission_config(self, reload: bool = False) -> Dict[str, Any]:
        """获取权限配置"""
        if self._permission_config is None or reload:
            self._permission_config = load_permission_config()
        return self._permission_config

    def get_form_config(self, form_name: str, reload: bool = False) -> Dict[str, Any]:
        """获取表单配置"""
        main_config = self.get_main_config(reload)
        forms_config = main_config.get("form_pages", {})

        if form_name not in forms_config:
            raise ValueError(f"表单 '{form_name}' 不存在")

        return load_form_config_by_name(form_name, forms_config)

    def get_table_config(self, table_name: str, reload: bool = False) -> Dict[str, Any]:
        """获取表格配置"""
        main_config = self.get_main_config(reload)
        tables_config = main_config.get("tables", {})

        if table_name not in tables_config:
            raise ValueError(f"表格 '{table_name}' 不存在")

        return load_table_config_by_name(table_name, tables_config)

    def get_all_form_configs(self, reload: bool = False) -> Dict[str, Dict[str, Any]]:
        """获取所有表单配置"""
        main_config = self.get_main_config(reload)
        forms_config = main_config.get("form_pages", {})

        result = {}
        for form_name in forms_config.keys():
            result[form_name] = self.get_form_config(form_name, reload)

        return result

    def get_all_table_configs(self, reload: bool = False) -> Dict[str, Dict[str, Any]]:
        """获取所有表格配置"""
        main_config = self.get_main_config(reload)
        tables_config = main_config.get("tables", {})

        result = {}
        for table_name in tables_config.keys():
            result[table_name] = self.get_table_config(table_name, reload)

        return result

    def get_active_form_config(self, reload: bool = False) -> Dict[str, Any]:
        """获取活动表单配置"""
        main_config = self.get_main_config(reload)
        active_form = main_config.get("active_form", "")

        if not active_form:
            raise ValueError("没有设置活动表单")

        return self.get_form_config(active_form, reload)

    def reload_all(self):
        """重新加载所有配置"""
        self.config_manager.clear_cache()
        self._main_config = None
        self._permission_config = None

        # 重新加载
        self.get_main_config(reload=True)
        self.get_permission_config(reload=True)

    def get_config_info(self) -> Dict[str, Any]:
        """获取配置信息"""
        main_config = self.get_main_config()
        permission_config = self.get_permission_config()

        return {
            "main_config": {
                "title": main_config.get("title"),
                "version": main_config.get("version"),
                "active_form": main_config.get("active_form"),
                "form_count": len(main_config.get("form_pages", {})),
                "table_count": len(main_config.get("tables", {})),
            },
            "permission_config": {
                "version": permission_config.get("version"),
                "check_order": permission_config.get("check_order"),
            },
            "cache_info": self.config_manager.get_cache_info(),
        }


# 全局配置加载器实例
_config_loader: Optional[ConfigLoader] = None


def get_config_loader() -> ConfigLoader:
    """获取配置加载器实例"""
    global _config_loader
    if _config_loader is None:
        _config_loader = ConfigLoader()
    return _config_loader


# 便捷函数
def get_main_config(reload: bool = False) -> Dict[str, Any]:
    """获取主配置（便捷函数）"""
    loader = get_config_loader()
    return loader.get_main_config(reload)


def get_permission_config(reload: bool = False) -> Dict[str, Any]:
    """获取权限配置（便捷函数）"""
    loader = get_config_loader()
    return loader.get_permission_config(reload)


def get_form_config(form_name: str, reload: bool = False) -> Dict[str, Any]:
    """获取表单配置（便捷函数）"""
    loader = get_config_loader()
    return loader.get_form_config(form_name, reload)


def get_table_config(table_name: str, reload: bool = False) -> Dict[str, Any]:
    """获取表格配置（便捷函数）"""
    loader = get_config_loader()
    return loader.get_table_config(table_name, reload)


def get_active_form_config(reload: bool = False) -> Dict[str, Any]:
    """获取活动表单配置（便捷函数）"""
    loader = get_config_loader()
    return loader.get_active_form_config(reload)


def reload_all_configs():
    """重新加载所有配置（便捷函数）"""
    loader = get_config_loader()
    loader.reload_all()


def get_config_info() -> Dict[str, Any]:
    """获取配置信息（便捷函数）"""
    loader = get_config_loader()
    return loader.get_config_info()


if __name__ == "__main__":
    import json

    # 测试统一配置加载器
    loader = get_config_loader()

    print("配置信息:")
    print(json.dumps(loader.get_config_info(), ensure_ascii=False, indent=2))

    print("\n主配置:")
    main_config = loader.get_main_config()
    print(f"标题: {main_config.get('title')}")
    print(f"活动表单: {main_config.get('active_form')}")

    print("\n活动表单配置:")
    active_form_config = loader.get_active_form_config()
    print(f"标题: {active_form_config.get('title')}")
    print(f"组数: {len(active_form_config.get('groups', {}))}")

    print("\n权限配置:")
    perm_config = loader.get_permission_config()
    print(f"检查顺序: {perm_config.get('check_order')}")

    # 测试热重载
    print("\n启用热重载:")
    get_config_manager().enable_hot_reload(True)

    # 测试重新加载
    print("\n重新加载所有配置:")
    loader.reload_all()

    print("重新加载后的配置信息:")
    print(json.dumps(loader.get_config_info(), ensure_ascii=False, indent=2))