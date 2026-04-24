"""
数据库操作。

Version: 1.0.0
负责 SQLite 连接、基础建表、种子数据写入与动态记录表结构生成。
"""
from __future__ import annotations

import os
import sqlite3
import json
from typing import Any

from app.core.config import get_config_service

FORM_RECORD_TABLE_PREFIX = "records_"


def _main_config_dict() -> dict[str, Any]:
    main = get_config_service().get_main_config()
    return {
        "data_paths": {
            "database": main.data_paths.database,
            "images": main.data_paths.images,
        },
        "form_pages": {k: {"title": v.title, "file": v.file} for k, v in main.form_pages.items()},
        "tables": {k: {"title": v.title, "file": v.file} for k, v in main.tables.items()},
        "database_config": {
            "journal_mode": main.database_config.journal_mode,
            "synchronous": main.database_config.synchronous,
            "foreign_keys": main.database_config.foreign_keys,
            "busy_timeout": main.database_config.busy_timeout,
            "cache_size": main.database_config.cache_size,
            "temp_store": main.database_config.temp_store,
            "mmap_size": main.database_config.mmap_size,
        },
    }


def apply_database_config(conn: sqlite3.Connection) -> None:
    """应用 config/main.yaml 中的 database 配置到 SQLite 连接"""
    db_cfg = _main_config_dict().get("database_config", {})
    cur = conn.cursor()
    # 应用 PRAGMA 设置
    journal_mode = db_cfg.get("journal_mode", "WAL")
    if journal_mode:
        cur.execute(f"PRAGMA journal_mode = {journal_mode}")
    synchronous = db_cfg.get("synchronous", "NORMAL")
    if synchronous:
        cur.execute(f"PRAGMA synchronous = {synchronous}")
    foreign_keys = db_cfg.get("foreign_keys", True)
    cur.execute(f"PRAGMA foreign_keys = {'ON' if foreign_keys else 'OFF'}")
    busy_timeout = db_cfg.get("busy_timeout", 5000)
    cur.execute(f"PRAGMA busy_timeout = {busy_timeout}")
    cache_size = db_cfg.get("cache_size", -2000)
    cur.execute(f"PRAGMA cache_size = {cache_size}")
    temp_store = db_cfg.get("temp_store", "DEFAULT")
    if temp_store:
        cur.execute(f"PRAGMA temp_store = {temp_store}")
    mmap_size = db_cfg.get("mmap_size", 268435456)
    cur.execute(f"PRAGMA mmap_size = {mmap_size}")
    cur.close()


def get_db() -> sqlite3.Connection:
    path = get_config_service().get_main_config().data_paths.database
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    apply_database_config(conn)
    return conn


def _normalize_col_type(type_expr: str) -> str:
    # Allow YAML using "STRING" to stay user-friendly while SQLite uses TEXT.
    return str(type_expr).replace("STRING", "TEXT")


def _expand_seed_row(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand list-valued fields into multiple rows for seed inserts."""
    expanded_rows: list[dict[str, Any]] = [dict(row)]
    for key, value in row.items():
        if not isinstance(value, list):
            continue
        if not value:
            for current in expanded_rows:
                current[key] = None
            continue
        next_rows: list[dict[str, Any]] = []
        for current in expanded_rows:
            for item in value:
                copied = dict(current)
                copied[key] = item
                next_rows.append(copied)
        expanded_rows = next_rows
    return expanded_rows


def _to_sql_value(value: Any) -> Any:
    """Normalize Python values to SQLite bindable values."""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return value


def _normalize_seed_insert_row(table_name: str, row: dict[str, Any]) -> dict[str, Any]:
    """Normalize seed rows before SQLite insert."""
    normalized = dict(row)
    if table_name != "permissions":
        return normalized

    raw_allowed = normalized.get("allowed", 1)
    if isinstance(raw_allowed, str):
        text = raw_allowed.strip().lower()
        if text in {"0", "false", "no", "off"}:
            normalized["allowed"] = 0
        elif text in {"1", "true", "yes", "on"}:
            normalized["allowed"] = 1
        else:
            normalized["allowed"] = 0
    elif isinstance(raw_allowed, int):
        normalized["allowed"] = raw_allowed
    else:
        normalized["allowed"] = 0
    return normalized


def init_db() -> None:
    conn = get_db()
    cursor = conn.cursor()

    config_service = get_config_service()
    for table_key in config_service.get_main_config().tables.keys():
        table_configs = config_service.get_table_config(table_key)
        cursor.execute(_normalize_col_type(table_configs["table_sql"]))
        table_name = str(table_configs.get("table_name", table_key))
        for raw_row in table_configs.get("seed_data", []):
            rows = [raw_row]
            if isinstance(raw_row, dict):
                rows = _expand_seed_row(raw_row)
            for row in rows:
                if not isinstance(row, dict) or not row:
                    continue
                row = _normalize_seed_insert_row(table_name, row)
                columns = [str(col).strip() for col in row.keys() if str(col).strip()]
                if not columns:
                    continue
                placeholders = ", ".join(["?"] * len(columns))
                sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"
                values = [_to_sql_value(row.get(col)) for col in columns]
                cursor.execute(sql, values)

    conn.commit()
    conn.close()


def _create_daily_records_indexes(cursor: sqlite3.Cursor, table_name: str) -> None:
    cursor.execute(f"PRAGMA table_info({table_name})")
    existing_cols = {str(row[1]) for row in cursor.fetchall()}
    index_targets = ("record_date", "fertilizer_id")
    for col in index_targets:
        if col in existing_cols:
            cursor.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{table_name}_{col} ON {table_name}({col})"
            )


def _build_daily_records_create_sql(table_name: str, fields: list[dict]) -> str:
    column_defs: dict[str, str] = {}

    def infer_sql_type(field: dict) -> str:
        explicit = str(field.get("db_type", "")).strip().upper()
        if explicit:
            return _normalize_col_type(explicit)
        key = str(field.get("key", ""))
        ftype = str(field.get("type", "text"))
        if key.endswith("_id"):
            return "INTEGER"
        if ftype == "number":
            return "REAL"
        if ftype == "date":
            return "DATE"
        return "TEXT"

    for f in fields:
        key = str(f.get("key", "")).strip()
        if not key or key in {"id", "created_at", "updated_at"}:
            continue
        if key in column_defs:
            continue
        sql_t = infer_sql_type(f)
        default = f.get("default")
        nullable = not bool(f.get("required", False))
        null_sql = "" if nullable else " NOT NULL"
        if default is not None and sql_t in {"TEXT", "DATE"}:
            safe_default = str(default).replace("'", "''")
            column_defs[key] = f"{key} {sql_t}{null_sql} DEFAULT '{safe_default}'"
        elif default is not None and sql_t in {"INTEGER", "REAL"}:
            column_defs[key] = f"{key} {sql_t}{null_sql} DEFAULT {default}"
        else:
            column_defs[key] = f"{key} {sql_t}{null_sql}"

    # 添加系统字段
    column_defs["created_at"] = "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    column_defs["updated_at"] = "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"

    ordered_keys = [k for k in column_defs.keys() if k not in {"created_at", "updated_at"}]
    ordered_keys.extend(["created_at", "updated_at"])
    cols_sql = ",\n            ".join(column_defs[k] for k in ordered_keys)

    return f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            {cols_sql}
        )
    """
