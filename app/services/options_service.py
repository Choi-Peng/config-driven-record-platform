"""
选项服务。

Version: 1.0.0
负责按配置从静态列表或数据库动态加载表单选项数据。
"""
from __future__ import annotations

from typing import Dict, List, Any, Optional
from app.core.config import get_config_service
from app.core.database import get_database_service
from app.core.exceptions import NotFoundError, ConfigError


class OptionsService:
    """选项服务"""

    def __init__(self):
        self.config_service = get_config_service()
        self.db_service = get_database_service()

    async def get_options(self, source_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        根据配置获取选项

        Args:
            source_config: 配置中的source字段

        Returns:
            选项列表，每个选项包含value, label, rawName等字段
        """
        if not source_config:
            return []

        source_type = source_config.get("type", "options")

        if source_type == "options":
            return self._get_static_options(source_config)
        elif source_type == "database":
            return await self._get_database_options(source_config)
        else:
            raise ConfigError(f"不支持的source类型: {source_type}")

    def _get_static_options(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """获取静态选项"""
        values = config.get("values", [])
        if not isinstance(values, list):
            return []

        options = []
        for value in values:
            if isinstance(value, dict):
                # 支持 {value: "val", label: "显示文本"} 格式
                option_value = str(value.get("value", ""))
                option_label = str(value.get("label", option_value))
                raw_name = str(value.get("rawName", option_label))
            else:
                # 简单值
                option_value = str(value)
                option_label = str(value)
                raw_name = str(value)

            if option_value:
                options.append({
                    "value": option_value,
                    "label": option_label,
                    "rawName": raw_name
                })

        return options

    async def _get_database_options(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从数据库获取选项"""
        values_config = config.get("values", {})
        table_name = values_config.get("table")
        key = values_config.get("key")

        if not table_name or not isinstance(key, str) or not key.strip():
            raise ConfigError("数据库source配置缺少 table 或 key 字段")
        key = key.strip()

        # 构建查询
        select_fields = ["id", key]
        table_info = self.db_service.fetchall(f"PRAGMA table_info({table_name})")
        all_columns = [str(col.get("name", "")).strip() for col in table_info if str(col.get("name", "")).strip()]
        enrich_columns = [c for c in ("type", "category", "group_name", "parent_name") if c in all_columns and c != key]
        for col in enrich_columns:
            if col not in select_fields:
                select_fields.append(col)
        has_deleted = any(str(col.get("name", "")) == "deleted" for col in table_info)
        where_sql = " WHERE deleted = 0 OR deleted IS NULL" if has_deleted else ""
        sql = f"SELECT {', '.join(select_fields)} FROM {table_name}{where_sql}"

        try:
            rows = self.db_service.fetchall(sql)
        except Exception as e:
            raise ConfigError(f"查询数据库失败: {e}")

        options = []
        seen_values: set[str] = set()
        for row in rows:
            primary_value = str(row.get(key, ""))
            if not primary_value.strip():
                continue
            if primary_value in seen_values:
                continue
            seen_values.add(primary_value)

            meta: dict[str, str] = {}
            raw_name_parts: list[str] = []
            for col in enrich_columns:
                col_val = str(row.get(col, "")).strip()
                if not col_val:
                    continue
                meta[col] = col_val
                raw_name_parts.append(col_val)
            raw_name_parts.append(primary_value)

            options.append({
                # Persist display text instead of id so record tables store readable values.
                "value": primary_value,
                "label": primary_value,
                "rawName": " ".join(raw_name_parts),
                "id": row.get("id"),
                "meta": meta,
            })

        return options

    async def get_dependent_options(self, source_config: Dict[str, Any], parent_value: str) -> List[Dict[str, Any]]:
        """
        获取依赖选项（如crop_names依赖于crop_variety）

        Args:
            source_config: 配置中的source字段
            parent_value: 父级选择的值

        Returns:
            过滤后的选项列表
        """
        if not parent_value:
            return []

        all_options = await self.get_options(source_config)

        # 这里可以根据具体依赖逻辑进行过滤
        # 例如：如果配置中有depends_on字段，可以根据父值过滤
        return all_options

    async def get_form_field_options(self, form_name: str, field_key: str) -> List[Dict[str, Any]]:
        """
        获取表单字段的选项

        Args:
            form_name: 表单名称
            field_key: 字段key

        Returns:
            选项列表
        """
        try:
            form_config = self.config_service.get_form_config(form_name)
            field = self._find_field_in_config(form_config, field_key)

            if not field:
                raise NotFoundError(f"字段未找到: {field_key}")

            source = field.get("source")
            if not source:
                return []

            return await self.get_options(source)

        except Exception as e:
            raise ConfigError(f"获取字段选项失败: {e}")

    def _find_field_in_config(self, form_config: Dict[str, Any], field_key: str) -> Optional[Dict[str, Any]]:
        """在表单配置中查找字段"""
        groups = form_config.get("groups", {})

        for group_key, group in groups.items():
            fields = group.get("fields", [])
            for field in fields:
                if field.get("key") == field_key:
                    return field

        return None


# 创建并注册服务
def create_options_service() -> OptionsService:
    """创建选项服务"""
    return OptionsService()


# 便捷函数
def get_options_service() -> OptionsService:
    """获取选项服务"""
    from app.core import get_container
    container = get_container()

    if "options" not in container._services:
        container.register("options", create_options_service())

    return container.get("options")


async def get_field_options(form_name: str, field_key: str) -> List[Dict[str, Any]]:
    """获取字段选项（便捷函数）"""
    service = get_options_service()
    return await service.get_form_field_options(form_name, field_key)


if __name__ == "__main__":
    # 测试选项服务
    import asyncio

    async def test():
        service = get_options_service()

        # 测试静态选项
        static_config = {
            "type": "options",
            "values": ["选项1", "选项2", "选项3"]
        }
        static_options = await service.get_options(static_config)
        print("静态选项:", static_options)

        # 测试数据库选项
        db_config = {
            "type": "database",
            "values": {
                "table": "fertilizers",
                "key": "name"
            }
        }
        try:
            db_options = await service.get_options(db_config)
            print("数据库选项:", db_options[:3])  # 只显示前3个
        except Exception as e:
            print(f"数据库选项测试失败: {e}")

    asyncio.run(test())