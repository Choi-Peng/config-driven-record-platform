"""
权限配置加载器。

Version: 1.0.0
负责加载权限策略配置并标准化权限顺序、默认规则、缓存与日志参数。
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Any
from . import get_config_manager


class PermissionConfigLoader:
    """权限配置加载器"""

    def __init__(self):
        self.config_manager = get_config_manager()
        self._default_config_path = self.config_manager.resolve_config_file("permissions.yaml")

    def _load_check_order(self, data: dict) -> list[str]:
        """加载权限检查顺序配置"""
        check_order = data.get("check_order", ["database", "file", "local"])
        if not isinstance(check_order, list):
            return ["database", "file", "local"]

        # 验证检查顺序的有效性
        valid_sources = ["database", "file", "local"]
        return [source for source in check_order if source in valid_sources]

    def _load_default_permissions(self, data: dict) -> dict:
        """加载默认权限配置"""
        default_perms = data.get("default_permissions", {})
        if not isinstance(default_perms, dict):
            return {}

        result = {
            "tables": {},
            "forms": {},
        }

        # 加载表默认权限
        table_defaults = default_perms.get("tables", {})
        if isinstance(table_defaults, dict):
            for role, perms in table_defaults.items():
                if isinstance(perms, dict):
                    result["tables"][role] = {
                        "read": perms.get("read", False),
                        "create": perms.get("create", False),
                        "update": perms.get("update", False),
                        "delete": perms.get("delete", False),
                    }

        # 加载表单默认权限
        form_defaults = default_perms.get("forms", {})
        if isinstance(form_defaults, dict):
            for role, perms in form_defaults.items():
                if isinstance(perms, dict):
                    result["forms"][role] = {
                        "read": perms.get("read", False),
                        "create": perms.get("create", False),
                        "update": perms.get("update", False),
                        "delete": perms.get("delete", False),
                    }

        return result

    def _load_file_permissions(self, data: dict) -> dict:
        """加载文件级权限配置"""
        file_perms = data.get("file_permissions", {})
        if not isinstance(file_perms, dict):
            return {}

        result = {
            "tables": {},
            "forms": {},
        }

        # 加载表权限
        for table_name, perms in file_perms.items():
            if table_name == "forms":
                continue  # 表单权限单独处理

            if isinstance(perms, dict):
                result["tables"][table_name] = {
                    "read": perms.get("read", []),
                    "create": perms.get("create", []),
                    "update": perms.get("update", []),
                    "delete": perms.get("delete", []),
                }

        # 加载表单权限
        forms_perms = file_perms.get("forms", {})
        if isinstance(forms_perms, dict):
            for form_name, perms in forms_perms.items():
                if isinstance(perms, dict):
                    result["forms"][form_name] = {
                        "read": perms.get("read", []),
                        "create": perms.get("create", []),
                        "update": perms.get("update", []),
                        "delete": perms.get("delete", []),
                    }

        return result

    def _load_permission_groups(self, data: dict) -> dict:
        """加载权限组配置"""
        groups = data.get("permission_groups", {})
        if not isinstance(groups, dict):
            return {}

        result = {}
        for group_name, group_data in groups.items():
            if isinstance(group_data, dict):
                result[group_name] = {
                    "description": group_data.get("description", ""),
                    "permissions": {
                        "tables": group_data.get("permissions", {}).get("tables", []),
                        "forms": group_data.get("permissions", {}).get("forms", []),
                    }
                }

        return result

    def _load_role_groups(self, data: dict) -> dict:
        """加载角色到权限组的映射"""
        role_groups = data.get("role_groups", {})
        if not isinstance(role_groups, dict):
            return {}

        result = {}
        for role, groups in role_groups.items():
            if isinstance(groups, list):
                result[role] = groups

        return result

    def _load_cache_config(self, data: dict) -> dict:
        """加载缓存配置"""
        cache_cfg = data.get("cache", {})
        if not isinstance(cache_cfg, dict):
            return {}

        return {
            "enabled": bool(cache_cfg.get("enabled", True)),
            "ttl": int(cache_cfg.get("ttl", 300)),
            "max_size": int(cache_cfg.get("max_size", 1000)),
        }

    def _load_logging_config(self, data: dict) -> dict:
        """加载日志配置"""
        logging_cfg = data.get("logging", {})
        if not isinstance(logging_cfg, dict):
            return {}

        return {
            "enabled": bool(logging_cfg.get("enabled", True)),
            "level": str(logging_cfg.get("level", "info")).lower(),
            "log_denied": bool(logging_cfg.get("log_denied", True)),
        }

    def load(self, path: str | Path = None) -> Dict[str, Any]:
        """
        加载权限配置

        Args:
            path: 权限配置文件路径，默认为 config/permissions.yaml

        Returns:
            dict: 权限配置数据
        """
        if path is None:
            path = self._default_config_path
        else:
            path_obj = Path(path)
            if path_obj.is_absolute():
                path = path_obj.resolve()
            else:
                path = self.config_manager.resolve_config_file(str(path_obj))

        # 检查缓存
        cache_key = self.config_manager._get_cache_key("permission")
        if self.config_manager._is_cache_valid(cache_key, str(path)):
            return self.config_manager._config_cache[cache_key]

        # 检查文件是否存在
        if not self.config_manager._check_file_exists(path):
            # 如果文件不存在，使用默认配置
            result = self._get_default_config()
        else:
            # 读取配置文件
            data = self.config_manager._read_yaml(path)

            # 构建结果
            result = {
                "version": data.get("version", "1.0"),
                "check_order": self._load_check_order(data),
                "default_permissions": self._load_default_permissions(data),
                "file_permissions": self._load_file_permissions(data),
                "permission_groups": self._load_permission_groups(data),
                "role_groups": self._load_role_groups(data),
                "cache": self._load_cache_config(data),
                "logging": self._load_logging_config(data),
            }

        # 更新缓存
        self.config_manager._update_cache(cache_key, str(path), result)

        return result

    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置（当配置文件不存在时使用）"""
        return {
            "version": "1.0",
            "check_order": ["database", "file", "local"],
            "default_permissions": {
                "tables": {
                    "admin": {"read": True, "create": True, "update": True, "delete": True},
                    "viewer": {"read": True, "create": False, "update": False, "delete": False},
                },
                "forms": {
                    "admin": {"read": True, "create": True, "update": True, "delete": True},
                    "viewer": {"read": True, "create": True, "update": True, "delete": False},
                },
            },
            "file_permissions": {
                "tables": {},
                "forms": {},
            },
            "permission_groups": {},
            "role_groups": {},
            "cache": {
                "enabled": True,
                "ttl": 300,
                "max_size": 1000,
            },
            "logging": {
                "enabled": True,
                "level": "info",
                "log_denied": True,
            },
        }


# 全局权限配置加载器实例
_permission_config_loader: PermissionConfigLoader = None


def get_permission_config_loader() -> PermissionConfigLoader:
    """获取权限配置加载器实例"""
    global _permission_config_loader
    if _permission_config_loader is None:
        _permission_config_loader = PermissionConfigLoader()
    return _permission_config_loader


def load_permission_config(path: str | Path = None) -> Dict[str, Any]:
    """加载权限配置（便捷函数）"""
    loader = get_permission_config_loader()
    return loader.load(path)


if __name__ == "__main__":
    import json

    # 测试权限配置加载
    config = load_permission_config()
    print(json.dumps(config, ensure_ascii=False, indent=2))

    # 测试缓存
    print("\n第二次加载（应该从缓存读取）:")
    config2 = load_permission_config()
    print(f"配置相同: {config == config2}")

    # 测试缓存信息
    print("\n缓存信息:")
    print(json.dumps(get_config_manager().get_cache_info(), ensure_ascii=False, indent=2))