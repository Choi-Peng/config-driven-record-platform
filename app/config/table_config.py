"""
表格配置加载器

加载和管理表格配置文件 (config/tables/*.yaml)
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Any
from . import get_config_manager


SQL_TEMPLATE = """CREATE TABLE IF NOT EXISTS {table_name} (
    {table_body}
);"""
SQL_COLUMN_TEMPLATE = "{column_key} {column_value}"
SQL_FOREIGN_KEY_TEMPLATE = "FOREIGN KEY ({column_key}) REFERENCES {foreign_key_value}"


class TableConfigLoader:
    def _normalize_foreign_key_ref(self, ref: str) -> str:
        raw = str(ref).strip()
        if "." in raw and "(" not in raw and ")" not in raw:
            table, col = raw.split(".", 1)
            table = table.strip()
            col = col.strip()
            if table and col:
                return f"{table}({col})"
        return raw

    """表格配置加载器"""

    def __init__(self):
        self.config_manager = get_config_manager()

    def _build_create_table_sql(
        self,
        table_name: str,
        columns: Dict[str, str],
        foreign_keys: Dict[str, str] | None = None,
    ) -> str:
        """构建创建表的SQL语句"""
        columns_sql = [
            SQL_COLUMN_TEMPLATE.format(column_key=k, column_value=v)
            for k, v in columns.items()
        ]

        foreign_keys_sql = [
            SQL_FOREIGN_KEY_TEMPLATE.format(
                column_key=k,
                foreign_key_value=self._normalize_foreign_key_ref(v),
            )
            for k, v in foreign_keys.items()
        ] if foreign_keys else []

        table_body = ",\n    ".join(columns_sql + foreign_keys_sql)
        return SQL_TEMPLATE.format(table_name=table_name, table_body=table_body)

    def _load_db_info(self, data: dict) -> dict:
        """加载数据库信息"""
        db_info = data.get("db_info") if isinstance(data.get("db_info"), dict) else {}
        table_name = db_info.get("table_name")
        if not table_name:
            raise ValueError("table_name is required")

        columns = db_info.get("columns")
        if not columns:
            raise ValueError("columns is required")

        foreign_keys = db_info.get("foreign_keys")
        table_sql = self._build_create_table_sql(
            table_name,
            columns,
            foreign_keys if foreign_keys else None,
        )

        return {
            "table_name": table_name,
            "table_sql": table_sql,
        }

    def _load_seed_data(self, data: dict, table_name: str) -> list:
        """加载种子数据"""
        seed_data = data.get("seed_data")
        return seed_data if isinstance(seed_data, list) else []

    def load(self, path: str | Path) -> Dict[str, Any]:
        """
        加载表格配置

        Args:
            path: 表格配置文件路径

        Returns:
            dict: 表格配置数据
        """
        path_obj = Path(path)
        if path_obj.is_absolute():
            path = path_obj.resolve()
        else:
            path = self.config_manager.resolve_config_file(str(path_obj))

        # 检查缓存
        cache_key = self.config_manager._get_cache_key("table", str(path))
        if self.config_manager._is_cache_valid(cache_key, str(path)):
            return self.config_manager._config_cache[cache_key]

        # 读取配置文件
        data = self.config_manager._read_yaml(path)

        # 加载数据库信息
        db_info = self._load_db_info(data)
        table_name = db_info.get("table_name")
        table_sql = db_info.get("table_sql")

        # 加载种子数据
        seed_data = self._load_seed_data(data, table_name)

        # 构建结果
        result = {
            "version": data.get("version", ""),
            "title": data.get("title", ""),
            "table_name": table_name,
            "table_sql": table_sql,
            "seed_data": seed_data,
            "column_mapping": data.get("column_mapping", {}),
            "column_labels": data.get("column_labels", {}),
            "show_columns": data.get("show_columns", []),
            "editable_columns": data.get("editable_columns", []),
            "permissions": data.get("permissions", {}),
        }

        # 更新缓存
        self.config_manager._update_cache(cache_key, str(path), result)

        return result

    def load_by_name(self, table_name: str, tables_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        通过表格名称加载配置

        Args:
            table_name: 表格名称
            tables_config: 表格配置字典（来自主配置）

        Returns:
            dict: 表格配置数据
        """
        if table_name not in tables_config:
            raise ValueError(f"表格 '{table_name}' 不存在")

        table_info = tables_config[table_name]
        table_file = table_info.get("file")

        if not table_file:
            raise ValueError(f"表格 '{table_name}' 没有配置文件路径")

        return self.load(table_file)


# 全局表格配置加载器实例
_table_config_loader: TableConfigLoader = None


def get_table_config_loader() -> TableConfigLoader:
    """获取表格配置加载器实例"""
    global _table_config_loader
    if _table_config_loader is None:
        _table_config_loader = TableConfigLoader()
    return _table_config_loader


def load_table_config(path: str | Path) -> Dict[str, Any]:
    """加载表格配置（便捷函数）"""
    loader = get_table_config_loader()
    return loader.load(path)


def load_table_config_by_name(table_name: str, tables_config: Dict[str, Any]) -> Dict[str, Any]:
    """通过表格名称加载配置（便捷函数）"""
    loader = get_table_config_loader()
    return loader.load_by_name(table_name, tables_config)


if __name__ == "__main__":
    import json

    # 测试表格配置加载
    test_path = "/Users/choi/好时吉/记录系统/config/tables/experiments.yaml"
    config = load_table_config(test_path)
    print(json.dumps(config, ensure_ascii=False, indent=2))

    # 测试SQL生成
    print("\n生成的SQL:")
    print(config["table_sql"])

    # 测试缓存
    print("\n第二次加载（应该从缓存读取）:")
    config2 = load_table_config(test_path)
    print(f"配置相同: {config == config2}")

    # 测试缓存信息
    print("\n缓存信息:")
    print(json.dumps(get_config_manager().get_cache_info(), ensure_ascii=False, indent=2))