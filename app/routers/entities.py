"""
通用实体管理路由。

Version: 1.0.0
基于表配置提供元数据、列表、创建、更新、删除等后台管理接口。
"""
from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.auth import require_permission
from app.core.config import get_config_service
from app.core.database import get_database_service

router = APIRouter(prefix="/api/entities", tags=["entities"])
db_service = get_database_service()

SYSTEM_FIELDS = {"id", "created_at", "modified_at", "deleted", "deleted_at", "deleted_by"}
IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_ident(name: str) -> str:
    ident = str(name).strip()
    if not IDENT_RE.fullmatch(ident):
        raise HTTPException(status_code=500, detail=f"非法标识符: {name}")
    return ident


def _parse_column_mapping(meta: dict[str, Any]) -> dict[str, dict[str, str]]:
    raw = meta.get("column_mapping")
    if not isinstance(raw, dict):
        return {}
    parsed: dict[str, dict[str, str]] = {}
    for alias_raw, expr_raw in raw.items():
        alias = _safe_ident(str(alias_raw))
        expr = str(expr_raw).strip()
        if "#" not in expr or "." not in expr:
            raise HTTPException(status_code=500, detail=f"column_mapping 配置错误: {alias}")
        source_col_raw, ref_raw = expr.split("#", 1)
        ref_table_raw, ref_value_col_raw = ref_raw.split(".", 1)
        source_col = _safe_ident(source_col_raw)
        ref_table = _safe_ident(ref_table_raw)
        ref_value_col = _safe_ident(ref_value_col_raw)
        parsed[alias] = {
            "source_col": source_col,
            "ref_table": ref_table,
            "ref_value_col": ref_value_col,
            "ref_id_col": "id",
        }
    return parsed


def _resolve_mapped_fk_value(
    mapping: dict[str, str],
    value: Any,
) -> Any:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    ref_table = mapping["ref_table"]
    ref_value_col = mapping["ref_value_col"]
    ref_id_col = mapping["ref_id_col"]
    ref_cols = _table_columns(ref_table)
    where_sql = ""
    if "deleted" in ref_cols:
        where_sql = " AND deleted = 0"
    row = db_service.fetchone(
        f"SELECT {ref_id_col} FROM {ref_table} WHERE {ref_value_col} = ?{where_sql} LIMIT 1",
        (value,),
    )
    if not row:
        raise HTTPException(status_code=400, detail=f"映射值不存在: {value}")
    return row.get(ref_id_col)


def _map_payload_to_db_columns(
    payload: dict[str, Any],
    mapping_config: dict[str, dict[str, str]],
) -> dict[str, Any]:
    data = dict(payload)
    for alias, mapping in mapping_config.items():
        if alias not in data:
            continue
        source_col = mapping["source_col"]
        if source_col in data:
            data.pop(alias, None)
            continue
        source_value = _resolve_mapped_fk_value(mapping, data[alias])
        data[source_col] = source_value
        data.pop(alias, None)
    return data


def _build_select_columns(
    table_name: str,
    show_columns: list[str],
    actual_columns: list[str],
    mapping_config: dict[str, dict[str, str]],
) -> str:
    actual_set = set(actual_columns)
    select_parts: list[str] = []
    for col in show_columns:
        if col in actual_set:
            select_parts.append(col)
            continue
        mapping = mapping_config.get(col)
        if not mapping:
            raise HTTPException(status_code=500, detail=f"展示字段不存在: {col}")
        source_col = mapping["source_col"]
        ref_table = mapping["ref_table"]
        ref_value_col = mapping["ref_value_col"]
        ref_id_col = mapping["ref_id_col"]
        expr = (
            f"(SELECT {ref_value_col} FROM {ref_table} "
            f"WHERE {ref_table}.{ref_id_col} = {table_name}.{source_col} LIMIT 1) AS {col}"
        )
        select_parts.append(expr)
    return ", ".join(select_parts)


def _inherit_viewer_permissions_for_role(conn, role_name: str) -> None:
    """Clone viewer permissions for a newly created role."""
    new_role = str(role_name).strip()
    if not new_role or new_role == "viewer":
        return
    if not db_service.table_exists("permissions", thread_safe=False):
        return

    permission_cols = {c.get("name") for c in db_service.get_table_info("permissions", thread_safe=False)}
    required_cols = {"resource_type", "resource_name", "action", "role_name"}
    if not required_cols.issubset(permission_cols):
        return

    source_select = ["resource_type", "resource_name", "action", "allowed", "priority"]
    source_select = [c for c in source_select if c in permission_cols]
    where_deleted = " AND deleted = 0" if "deleted" in permission_cols else ""
    source_rows = db_service.fetchall(
        f"SELECT {', '.join(source_select)} FROM permissions WHERE role_name = ?{where_deleted}",
        ("viewer",),
        thread_safe=False,
    )
    if not source_rows:
        return

    insert_cols = ["resource_type", "resource_name", "action", "role_name"]
    for optional_col in ("allowed", "priority", "deleted"):
        if optional_col in permission_cols:
            insert_cols.append(optional_col)
    placeholders = ", ".join(["?"] * len(insert_cols))
    insert_sql = f"INSERT INTO permissions ({', '.join(insert_cols)}) VALUES ({placeholders})"

    cur = conn.connection.cursor()
    for row in source_rows:
        values: list[Any] = []
        for col in insert_cols:
            if col == "role_name":
                values.append(new_role)
            elif col == "deleted":
                values.append(0)
            else:
                values.append(row.get(col))
        cur.execute(insert_sql, values)


def _table_meta(table_key: str) -> dict[str, Any]:
    cfg_service = get_config_service()
    main = cfg_service.get_main_config()
    if table_key not in main.tables:
        raise HTTPException(status_code=404, detail="未知表配置")
    meta = cfg_service.get_table_config(table_key)
    table_name = str(meta.get("table_name", "")).strip()
    if not table_name:
        raise HTTPException(status_code=500, detail="表配置缺少 table_name")
    return meta


def _table_columns(table_name: str) -> list[str]:
    rows = db_service.fetchall(f"PRAGMA table_info({table_name})")
    return [str(r.get("name", "")).strip() for r in rows if str(r.get("name", "")).strip()]


def _editable_columns(meta: dict[str, Any], actual_columns: list[str]) -> list[str]:
    configured = meta.get("editable_columns")
    if isinstance(configured, list) and configured:
        cols = [str(c).strip() for c in configured if str(c).strip()]
        return [c for c in cols if c in actual_columns and c not in SYSTEM_FIELDS]

    show_cols = meta.get("show_columns")
    if isinstance(show_cols, list) and show_cols:
        cols = [str(c).strip() for c in show_cols if str(c).strip()]
        out = [c for c in cols if c in actual_columns and c not in SYSTEM_FIELDS]
        if out:
            return out

    return [c for c in actual_columns if c not in SYSTEM_FIELDS]


def _column_labels(meta: dict[str, Any]) -> dict[str, str]:
    raw = meta.get("column_labels")
    if not isinstance(raw, dict):
        return {}
    labels: dict[str, str] = {}
    for key, value in raw.items():
        k = str(key).strip()
        if not k:
            continue
        labels[k] = str(value).strip() or k
    return labels


@router.get("/{table_key}/meta")
async def get_entity_meta(table_key: str, request: Request):
    await require_permission(request, "table", table_key, "read")
    meta = _table_meta(table_key)
    table_name = str(meta["table_name"])
    cols = _table_columns(table_name)
    return {
        "table_key": table_key,
        "table_name": table_name,
        "title": meta.get("title", table_key),
        "show_columns": meta.get("show_columns", []),
        "editable_columns": _editable_columns(meta, cols),
        "column_labels": _column_labels(meta),
        "columns": cols,
    }


@router.get("/{table_key}")
async def list_entities(table_key: str, request: Request):
    await require_permission(request, "table", table_key, "read")
    meta = _table_meta(table_key)
    table_name = str(meta["table_name"])
    show_columns = [str(c).strip() for c in meta.get("show_columns", []) if str(c).strip()]
    cols = _table_columns(table_name)
    mapping_config = _parse_column_mapping(meta)
    if not show_columns:
        show_columns = [c for c in cols if c != "deleted"]
    if "id" in cols and "id" not in show_columns:
        show_columns = ["id"] + show_columns
    select_cols = _build_select_columns(table_name, show_columns, cols, mapping_config)
    where_sql = " WHERE deleted = 0" if "deleted" in cols else ""
    order_sql = " ORDER BY id DESC" if "id" in cols else ""
    rows = db_service.fetchall(f"SELECT {select_cols} FROM {table_name}{where_sql}{order_sql}")
    return {"items": rows}


@router.post("/{table_key}")
async def create_entity(table_key: str, payload: dict[str, Any], request: Request):
    await require_permission(request, "table", table_key, "create")
    meta = _table_meta(table_key)
    table_name = str(meta["table_name"])
    cols = _table_columns(table_name)
    mapping_config = _parse_column_mapping(meta)
    editable = set(_editable_columns(meta, cols))
    configured_editable = {
        str(c).strip() for c in meta.get("editable_columns", []) if str(c).strip()
    }
    mapped_editable_aliases = {k for k in configured_editable if k in mapping_config}
    allowed_payload_fields = editable | mapped_editable_aliases
    payload_data = {k: v for k, v in payload.items() if k in allowed_payload_fields}
    mapped_data = _map_payload_to_db_columns(payload_data, mapping_config)
    mapped_target_cols = {mapping_config[k]["source_col"] for k in mapped_editable_aliases}
    writable_db_cols = editable | mapped_target_cols
    write_data = {k: v for k, v in mapped_data.items() if k in writable_db_cols and k in cols}
    if not write_data:
        raise HTTPException(status_code=400, detail="没有可写入字段")

    keys = list(write_data.keys())
    placeholders = ", ".join(["?"] * len(keys))
    sql = f"INSERT INTO {table_name} ({', '.join(keys)}) VALUES ({placeholders})"
    conn = db_service.get_connection(thread_safe=False)
    try:
        cur = conn.connection.cursor()
        cur.execute(sql, [write_data[k] for k in keys])
        if table_key == "roles" and isinstance(write_data.get("name"), str):
            _inherit_viewer_permissions_for_role(conn, str(write_data["name"]))
        conn.commit()
        return {"success": True, "id": cur.lastrowid}
    finally:
        conn.close()


@router.put("/{table_key}/{entity_id}")
async def update_entity(table_key: str, entity_id: int, payload: dict[str, Any], request: Request):
    await require_permission(request, "table", table_key, "update")
    meta = _table_meta(table_key)
    table_name = str(meta["table_name"])
    cols = _table_columns(table_name)
    mapping_config = _parse_column_mapping(meta)
    editable = set(_editable_columns(meta, cols))
    configured_editable = {
        str(c).strip() for c in meta.get("editable_columns", []) if str(c).strip()
    }
    mapped_editable_aliases = {k for k in configured_editable if k in mapping_config}
    allowed_payload_fields = editable | mapped_editable_aliases
    payload_data = {k: v for k, v in payload.items() if k in allowed_payload_fields}
    mapped_data = _map_payload_to_db_columns(payload_data, mapping_config)
    mapped_target_cols = {mapping_config[k]["source_col"] for k in mapped_editable_aliases}
    writable_db_cols = editable | mapped_target_cols
    write_data = {k: v for k, v in mapped_data.items() if k in writable_db_cols and k in cols}
    if not write_data:
        raise HTTPException(status_code=400, detail="没有可更新字段")

    set_sql = ", ".join([f"{k}=?" for k in write_data.keys()])
    params = [write_data[k] for k in write_data.keys()]
    sql = f"UPDATE {table_name} SET {set_sql}"
    if "modified_at" in cols:
        sql = f"UPDATE {table_name} SET {set_sql}, modified_at=CURRENT_TIMESTAMP"
    sql += " WHERE id=?"
    params.append(entity_id)

    conn = db_service.get_connection(thread_safe=False)
    try:
        cur = conn.connection.cursor()
        cur.execute(sql, params)
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="记录不存在")
        return {"success": True}
    finally:
        conn.close()


@router.delete("/{table_key}/{entity_id}")
async def delete_entity(table_key: str, entity_id: int, request: Request):
    await require_permission(request, "table", table_key, "delete")
    meta = _table_meta(table_key)
    table_name = str(meta["table_name"])
    cols = _table_columns(table_name)
    conn = db_service.get_connection(thread_safe=False)
    try:
        cur = conn.connection.cursor()
        if "deleted" in cols:
            sql = f"UPDATE {table_name} SET deleted=1, modified_at=CURRENT_TIMESTAMP WHERE id=?"
            cur.execute(sql, (entity_id,))
        else:
            cur.execute(f"DELETE FROM {table_name} WHERE id=?", (entity_id,))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="记录不存在")
        return {"success": True}
    finally:
        conn.close()
