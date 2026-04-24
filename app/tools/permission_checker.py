"""
权限检查工具。

Version: 1.0.0
支持从数据库、配置文件与资源本地配置多来源合并判断权限。
"""
from __future__ import annotations

import time
from typing import Optional, Dict, Any

try:
    from app.core.config import get_config_service
    from app.core.database import get_database_service
except ImportError:
    from core.config import get_config_service
    from core.database import get_database_service


class PermissionCache:
    """权限缓存"""

    def __init__(self, max_size: int = 1000, ttl: int = 300):
        self.max_size = max_size
        self.ttl = ttl
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.timestamps: Dict[str, float] = {}

    def _make_key(self, role: str, resource_type: str, resource_name: str, action: str) -> str:
        """生成缓存键"""
        return f"{role}:{resource_type}:{resource_name}:{action}"

    def get(self, role: str, resource_type: str, resource_name: str, action: str) -> Optional[Dict[str, Any]]:
        """从缓存获取权限检查结果"""
        key = self._make_key(role, resource_type, resource_name, action)

        if key not in self.cache:
            return None

        # 检查是否过期
        if time.time() - self.timestamps.get(key, 0) > self.ttl:
            self.delete(key)
            return None

        return self.cache[key]

    def set(self, role: str, resource_type: str, resource_name: str, action: str, result: Dict[str, Any]):
        """设置缓存"""
        key = self._make_key(role, resource_type, resource_name, action)

        # 如果缓存已满，删除最旧的条目
        if len(self.cache) >= self.max_size:
            oldest_key = min(self.timestamps.items(), key=lambda x: x[1])[0]
            self.delete(oldest_key)

        self.cache[key] = result
        self.timestamps[key] = time.time()

    def delete(self, key: str):
        """删除缓存条目"""
        if key in self.cache:
            del self.cache[key]
        if key in self.timestamps:
            del self.timestamps[key]

    def clear(self):
        """清空缓存"""
        self.cache.clear()
        self.timestamps.clear()


class PermissionChecker:
    """权限检查器"""

    def __init__(self, db_connection=None, config_path: Optional[str] = None):
        """
        初始化权限检查器

        Args:
            db_connection: 数据库连接（可选）
            config_path: 权限配置文件路径（可选）
        """
        self.db = db_connection
        self.db_service = get_database_service()
        config_service = get_config_service()
        self.config = config_service.get_permission_config(force_reload=bool(config_path))

        # 初始化缓存
        cache_cfg = self.config.get("cache", {})
        self.cache = PermissionCache(
            max_size=cache_cfg.get("max_size", 1000),
            ttl=cache_cfg.get("ttl", 300)
        )

        # 日志配置
        self.logging_cfg = self.config.get("logging", {})

    def check_database_permission(self, role: str, resource_type: str, resource_name: str, action: str) -> Optional[bool]:
        """检查数据库中的权限"""
        try:
            # 查询数据库权限表，优先级最高的记录生效；allowed=0 表示显式拒绝。
            if not self.db_service.table_exists("permissions", thread_safe=True):
                return None

            cols = self.db_service.get_table_info("permissions", thread_safe=True)
            col_names = {str(c.get("name", "")).strip() for c in cols}
            where_deleted = " AND deleted = 0" if "deleted" in col_names else ""
            query = """
                SELECT allowed
                FROM permissions
                WHERE resource_type = ?
                  AND resource_name = ?
                  AND action = ?
                  AND role_name = ?
            """ + where_deleted + """
                ORDER BY priority DESC, id DESC
                LIMIT 1
            """
            for name in self._resource_name_candidates(resource_type, resource_name):
                result = self.db_service.fetchone(
                    query,
                    (resource_type, name, action, role),
                    thread_safe=True,
                )
                if not result:
                    continue
                return bool(int(result.get("allowed", 0)))
            return None
        except Exception as e:
            self._log_error(f"数据库权限检查失败: {e}")
            return None

    def check_file_permission(self, role: str, resource_type: str, resource_name: str, action: str) -> Optional[bool]:
        """检查文件配置中的权限"""
        file_perms = self.config.get("file_permissions", {})

        if resource_type == "table":
            table_perms = file_perms.get("tables", {}).get(resource_name, {})
            allowed_roles = table_perms.get(action, [])
            return role in allowed_roles if allowed_roles else None

        elif resource_type == "form":
            forms_cfg = file_perms.get("forms", {})
            for name in self._resource_name_candidates(resource_type, resource_name):
                form_perms = forms_cfg.get(name, {})
                allowed_roles = form_perms.get(action, [])
                if allowed_roles:
                    return role in allowed_roles
            return None

        return None

    def check_local_permission(self, role: str, resource_type: str, resource_name: str, action: str,
                               local_config: Optional[Dict] = None) -> Optional[bool]:
        """检查本地配置中的权限"""
        if not local_config:
            return None

        permissions = local_config.get("permissions", {})
        allowed_roles = permissions.get(action, [])

        return role in allowed_roles if allowed_roles else None

    def get_default_permission(self, role: str, resource_type: str, action: str) -> bool:
        """获取默认权限"""
        default_perms = self.config.get("default_permissions", {})

        if resource_type == "table":
            role_perms = default_perms.get("tables", {}).get(role, {})
            return role_perms.get(action, False)

        elif resource_type == "form":
            role_perms = default_perms.get("forms", {}).get(role, {})
            return role_perms.get(action, False)

        return False

    @staticmethod
    def _expand_roles(role: str) -> list[str]:
        normalized = str(role or "").strip()
        if not normalized:
            return ["viewer"]
        aliases = {
            "user": "viewer",
        }
        alias = aliases.get(normalized)
        if alias and alias != normalized:
            return [normalized, alias]
        return [normalized]

    @staticmethod
    def _resource_name_candidates(resource_type: str, resource_name: str) -> list[str]:
        """Return normalized candidate names for permission lookup."""
        name = str(resource_name or "").strip()
        if not name:
            return [""]
        if resource_type != "form":
            return [name]
        prefix = "records_"
        candidates: list[str] = [name]
        if name.startswith(prefix):
            short_name = name[len(prefix):].strip()
            if short_name:
                candidates.append(short_name)
        else:
            candidates.append(f"{prefix}{name}")
        # Preserve order while deduplicating.
        out: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            out.append(candidate)
        return out

    def check(self, role: str, resource_type: str, resource_name: str, action: str,
              local_config: Optional[Dict] = None) -> bool:
        """
        检查权限

        Args:
            role: 用户角色
            resource_type: 资源类型 ('table' 或 'form')
            resource_name: 资源名称
            action: 操作类型 ('read', 'create', 'update', 'delete')
            local_config: 资源的本地配置（可选）

        Returns:
            bool: 是否允许该操作
        """
        roles_to_try = self._expand_roles(role)
        cache_role = "|".join(roles_to_try)

        # 1. 检查缓存
        cached_result = self.cache.get(cache_role, resource_type, resource_name, action)
        if cached_result is not None:
            return cached_result.get("allowed", False)

        # 2. 按照配置的顺序检查权限
        check_order = self.config.get("check_order", ["database", "file", "local"])
        result = None
        source = "default"

        for source_type in check_order:
            if source_type == "database":
                for single_role in roles_to_try:
                    result = self.check_database_permission(single_role, resource_type, resource_name, action)
                    if result is not None:
                        source = "database"
                        break
                if result is not None:
                    break

            elif source_type == "file":
                for single_role in roles_to_try:
                    result = self.check_file_permission(single_role, resource_type, resource_name, action)
                    if result is not None:
                        source = "file"
                        break
                if result is not None:
                    break

            elif source_type == "local":
                for single_role in roles_to_try:
                    result = self.check_local_permission(single_role, resource_type, resource_name, action, local_config)
                    if result is not None:
                        source = "local"
                        break
                if result is not None:
                    break

        # 3. 如果所有来源都没有配置，使用默认权限
        if result is None:
            for single_role in roles_to_try:
                result = self.get_default_permission(single_role, resource_type, action)
                if result:
                    break
            if result is None:
                result = False
            source = "default"

        # 4. 记录日志
        if not result and self.logging_cfg.get("log_denied", True):
            self._log_denied(role, resource_type, resource_name, action, source)

        # 5. 缓存结果
        cache_result = {
            "allowed": result,
            "source": source,
            "timestamp": time.time()
        }
        self.cache.set(cache_role, resource_type, resource_name, action, cache_result)

        return result

    def has_permission(self, role: str, resource_type: str, resource_name: str, action: str,
                       local_config: Optional[Dict] = None) -> bool:
        """检查是否有权限（check 的别名）"""
        return self.check(role, resource_type, resource_name, action, local_config)

    def get_user_permissions(self, role: str) -> Dict[str, Dict[str, bool]]:
        """获取用户的所有权限（简化版本）"""
        # 这里可以实现更复杂的逻辑，查询用户对所有资源的权限
        # 目前返回空字典，需要根据实际需求实现
        return {}

    def _log_denied(self, role: str, resource_type: str, resource_name: str, action: str, source: str):
        """记录被拒绝的权限检查"""
        level = self.logging_cfg.get("level", "info").lower()
        if level in ["debug", "info"]:
            message = f"权限拒绝: {role} 尝试 {action} {resource_type}/{resource_name} (来源: {source})"
            print(f"[PERMISSION] {message}")

    def _log_error(self, message: str):
        """记录错误日志"""
        level = self.logging_cfg.get("level", "info").lower()
        if level in ["debug", "info", "warn", "error"]:
            print(f"[PERMISSION ERROR] {message}")

    def clear_cache(self):
        """清空权限缓存"""
        self.cache.clear()


# 全局权限检查器实例（可选）
_permission_checker: Optional[PermissionChecker] = None


def get_permission_checker(db_connection=None, config_path: Optional[str] = None) -> PermissionChecker:
    """获取全局权限检查器实例"""
    global _permission_checker
    if _permission_checker is None:
        _permission_checker = PermissionChecker(db_connection, config_path)
    return _permission_checker


def check_permission(role: str, resource_type: str, resource_name: str, action: str,
                     local_config: Optional[Dict] = None) -> bool:
    """检查权限（便捷函数）"""
    checker = get_permission_checker()
    return checker.check(role, resource_type, resource_name, action, local_config)


if __name__ == "__main__":
    # 测试权限检查器
    checker = PermissionChecker()

    # 测试用例
    test_cases = [
        ("admin", "table", "experiments", "read"),
        ("viewer", "table", "experiments", "read"),
        ("admin", "table", "experiments", "delete"),
        ("viewer", "table", "experiments", "delete"),
        ("admin", "form", "open_field", "create"),
        ("viewer", "form", "open_field", "create"),
    ]

    print("权限检查测试:")
    print("-" * 60)

    for role, resource_type, resource_name, action in test_cases:
        allowed = checker.check(role, resource_type, resource_name, action)
        print(f"{role:10} {action:6} {resource_type:6} {resource_name:20} => {'允许' if allowed else '拒绝'}")

    print("-" * 60)