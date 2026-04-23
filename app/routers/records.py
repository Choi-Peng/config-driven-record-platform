import json
import re
from pathlib import Path
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, UploadFile
from starlette.datastructures import UploadFile as StarletteUploadFile
from app.auth import require_permission
from app.core.config import get_config_service
from app.core.database import get_database_service
from app.form_layout import load_merged_fields_for_schema
from app.tools.permission_checker import check_permission

router = APIRouter(prefix="/api/records", tags=["records"])
db_service = get_database_service()


def _is_upload_file(value: object) -> bool:
    return isinstance(value, (UploadFile, StarletteUploadFile))


def _images_upload_dir() -> Path:
    return Path(get_config_service().get_main_config().data_paths.images)


def _parse_images(raw: object) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw if str(x).strip()]
    if isinstance(raw, str):
        try:
            arr = json.loads(raw)
            if isinstance(arr, list):
                return [str(x) for x in arr if str(x).strip()]
        except Exception:
            return []
    return []


def _image_url_to_path(url: str) -> Path | None:
    raw = str(url or "").strip()
    if not raw.startswith("/images/"):
        return None
    rel = raw[len("/images/"):].strip()
    if not rel:
        return None
    rel_path = Path(rel)
    if rel_path.is_absolute():
        return None
    if any(part in {"", ".", ".."} for part in rel_path.parts):
        return None
    base = _images_upload_dir().resolve()
    target = (base / rel_path).resolve()
    if not str(target).startswith(str(base)):
        return None
    return target


def _safe_part(value: str | None, default: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return default
    s = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", raw)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or default


def _render_image_name_base(
    payload: dict[str, str],
    field_key: str,
    image_index: int,
    original_ext: str = ".png",
) -> str:
    main = get_config_service().get_main_config()
    form_page_key = str(payload.get("form_page", "")).strip() or "form"
    form_page_cfg = main.form_pages.get(form_page_key)
    form_page_title = form_page_cfg.title if form_page_cfg else form_page_key
    table_key = f"records_{form_page_key}"
    table_title = str(form_page_title)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

    fmt = str(getattr(main, "image_name_format", "") or "").strip()
    if not fmt:
        fmt = "{timestamp}_{image_index}"

    values = {
        "form_page_key": _safe_part(form_page_key, "form"),
        "form_page_title": _safe_part(form_page_title, "form"),
        "table_key": _safe_part(table_key, "table"),
        "table_title": _safe_part(table_title, "table"),
        "timestamp": timestamp,
        "image_index": str(image_index),
    }

    def resolve_dynamic_key(key: str) -> str:
        k = str(key or "").strip()
        if not k:
            return ""
        if k in payload:
            return _safe_part(str(payload.get(k, "")).strip(), "")
        if k in values:
            return str(values[k])
        return ""

    for token, token_value in values.items():
        fmt = fmt.replace(f"{{{token}}}", token_value)
    # Single-brace payload placeholders, e.g. {recorder} / {experiment_name}.
    def replace_single_brace_token(match: re.Match[str]) -> str:
        token = str(match.group(1) or "").strip()
        if token == "field_key":
            return _safe_part(field_key, "image")
        return resolve_dynamic_key(token)

    fmt = re.sub(r"\{([A-Za-z0-9_\-]+)\}", replace_single_brace_token, fmt)
    fmt = fmt.replace("{field_key}", _safe_part(field_key, "image"))
    fmt = re.sub(r"[^A-Za-z0-9_\-\u4e00-\u9fff.]+", "_", fmt)
    fmt = re.sub(r"_+", "_", fmt).strip("._")
    if not fmt:
        fmt = f"{values['form_page_key']}_{values['timestamp']}_{image_index}"
    ext = str(original_ext or ".png").strip().lower()
    if not ext.startswith("."):
        ext = f".{ext}"
    if ext not in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        ext = ".png"
    if "." not in fmt:
        fmt = f"{fmt}{ext}"
    return fmt


def _resolve_image_storage(payload: dict[str, str]) -> tuple[Path, str]:
    main = get_config_service().get_main_config()
    form_page_key = str(payload.get("form_page", "")).strip() or "form"
    form_page_cfg = main.form_pages.get(form_page_key)
    form_page_title = str(form_page_cfg.title if form_page_cfg else form_page_key).strip()
    folder_name = _safe_part(form_page_title, _safe_part(form_page_key, "form"))
    upload_dir = _images_upload_dir() / folder_name
    url_prefix = f"/images/{folder_name}"
    return upload_dir, url_prefix


async def _save_images_for_field(
    files: list[UploadFile],
    payload: dict[str, str],
    field_key: str,
    start_index: int = 1,
) -> list[str]:
    upload_dir, url_prefix = _resolve_image_storage(payload)
    upload_dir.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    allowed = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    image_index = max(1, int(start_index))
    for f in files:
        if not f or not f.filename:
            continue
        ext = Path(f.filename).suffix.lower()
        if ext not in allowed:
            continue
        base_name = _render_image_name_base(payload, field_key, image_index, ext)
        target = upload_dir / base_name
        while target.exists():
            image_index += 1
            base_name = _render_image_name_base(payload, field_key, image_index, ext)
            target = upload_dir / base_name
        data = await f.read()
        if not data:
            continue
        target.write_bytes(data)
        saved.append(f"{url_prefix}/{base_name}")
        image_index += 1
    return saved


def _extract_upload_files(form, field_key: str) -> list[UploadFile]:
    files: list[UploadFile] = []
    if hasattr(form, "getlist"):
        values = form.getlist(field_key)
    else:
        values = [form.get(field_key)]
    for value in values:
        if _is_upload_file(value):
            files.append(value)  # type: ignore[arg-type]
    return files


def _target_form_pages(form_page: str | None) -> list[str]:
    pages = get_config_service().get_main_config().form_pages
    if form_page:
        if form_page not in pages:
            raise HTTPException(status_code=400, detail="未知表单页面")
        return [form_page]
    return list(pages.keys())


def _safe_form_table_name(form_page: str) -> str:
    key = str(form_page).strip()
    if key not in get_config_service().get_main_config().form_pages:
        raise HTTPException(status_code=400, detail="未知表单页面")
    return f"records_{key}"


def _ensure_form_records_table(db_conn, cursor, page_key: str) -> str:
    table_name = _safe_form_table_name(page_key)
    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
    if not cursor.fetchone():
        from app.db import _build_daily_records_create_sql, _create_daily_records_indexes

        fields = load_merged_fields_for_schema(page_key)
        create_sql = _build_daily_records_create_sql(table_name, fields)
        cursor.execute(create_sql)
        _create_daily_records_indexes(cursor, table_name)
        db_conn.commit()
    return table_name


def _form_field_label_map(form_key: str) -> dict[str, str]:
    labels: dict[str, str] = {}
    for field in load_merged_fields_for_schema(form_key):
        key = str(field.get("key", "")).strip()
        if not key:
            continue
        labels[key] = str(field.get("label", key)).strip() or key
    labels.setdefault("record_date", "日期")
    labels.setdefault("record_time", "时间")
    return labels


def _get_form_show_columns(form_key: str) -> list[str]:
    form_config = get_config_service().get_form_config(form_key)
    raw = form_config.get("show_columns")
    if isinstance(raw, list):
        out = [str(c).strip() for c in raw if str(c).strip()]
        if out:
            return out
    return ["record_date", "record_time", "recorder"]


def _map_payload_to_allowed_columns(payload: dict[str, Any], allowed_cols: set[str]) -> dict[str, Any]:
    mapped: dict[str, Any] = {}
    for raw_key, value in payload.items():
        key = str(raw_key).strip()
        if key and key in allowed_cols:
            mapped[key] = value
    return mapped


@router.get("")
async def get_records(
    request: Request,
    form_page: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
):
    viewer = request.session.get("viewer") or {"role_name": "viewer"}
    role = str(viewer.get("role_name", "viewer"))

    db_conn = db_service.get_connection(thread_safe=False)
    cursor = db_conn.connection.cursor()

    records: list[dict] = []
    for page_key in _target_form_pages(form_page):
        if not check_permission(role, "form", page_key, "read"):
            continue
        table_name = _ensure_form_records_table(db_conn, cursor, page_key)

        query = f"SELECT dr.* FROM {table_name} dr WHERE 1=1"
        params: list[object] = []
        if start_date:
            query += " AND dr.record_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND dr.record_date <= ?"
            params.append(end_date)
        query += " ORDER BY dr.record_date DESC"
        cursor.execute(query, params)
        for row in cursor.fetchall():
            item = dict(row)
            item["form_page"] = page_key
            records.append(item)

    records.sort(key=lambda r: str(r.get("form_page") or ""))
    records.sort(key=lambda r: str(r.get("record_date") or ""), reverse=True)
    for r in records:
        imgs = _parse_images(r.get("images"))
        r["image_count"] = len(imgs)
    db_conn.close()
    return {"records": records}


@router.get("/columns")
async def get_records_columns(request: Request, form_page: str | None = None):
    """
    获取记录表格的列配置

    根据所有表单的字段配置动态生成表格列
    """
    viewer = request.session.get("viewer") or {"role_name": "viewer"}
    role = str(viewer.get("role_name", "viewer"))

    page_keys = _target_form_pages(form_page)
    allowed_pages = [p for p in page_keys if check_permission(role, "form", p, "read")]
    if not allowed_pages:
        return {"columns": []}

    labels_by_key: dict[str, str] = {}
    merged_show_cols: list[str] = []
    seen: set[str] = set()
    for page_key in allowed_pages:
        labels_by_key.update(_form_field_label_map(page_key))
        for col in _get_form_show_columns(page_key):
            if col not in seen:
                seen.add(col)
                merged_show_cols.append(col)

    columns: list[dict[str, Any]] = []
    if form_page is None:
        columns.append({"key": "form_page", "label": "环境", "width": "90px"})
    for col in merged_show_cols:
        columns.append({"key": col, "label": labels_by_key.get(col, col), "width": "120px"})
    columns.append({"key": "actions", "label": "操作", "width": "180px"})
    return {"columns": columns}


@router.post("")
async def create_record(
    request: Request,
):
    # 获取当前表单页面
    form_data = await request.form()
    page_key = str(form_data.get("form_page") or form_data.get("page_key") or "open_field")
    await require_permission(request, "form", page_key, "create")

    db_conn = db_service.get_connection(thread_safe=False)
    cursor = db_conn.connection.cursor()
    try:
        form = await request.form()
        payload: dict[str, str] = {}
        for k, v in form.multi_items():
            if _is_upload_file(v):
                continue
            key = str(k).strip()
            val = str(v).strip()
            if not key or val == "":
                continue
            payload[key] = val

        form_page = payload.get("form_page", "default")
        record_date = payload.get("record_date")
        if not record_date:
            return {"success": False, "message": "缺少 record_date"}
        table_name = _safe_form_table_name(form_page)

        # 检查表是否存在，如果不存在则创建
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
        if not cursor.fetchone():
            # 创建表单记录表
            from app.db import _build_daily_records_create_sql, _create_daily_records_indexes

            # 获取表单字段配置
            fields = load_merged_fields_for_schema(form_page)
            create_sql = _build_daily_records_create_sql(table_name, fields)
            cursor.execute(create_sql)
            _create_daily_records_indexes(cursor, table_name)
            db_conn.commit()

        image_fields = [
            f for f in load_merged_fields_for_schema(form_page)
            if str(f.get("type", "")).strip() in {"image", "file"}
        ]
        next_index = 1
        for field in image_fields:
            field_key = str(field.get("key", "")).strip()
            if not field_key:
                continue
            files = _extract_upload_files(form, field_key)
            if not files:
                continue
            image_urls = await _save_images_for_field(files, payload, field_key, next_index)
            if image_urls:
                payload[field_key] = json.dumps(image_urls, ensure_ascii=False)
                next_index += len(image_urls)
                continue
            # Avoid persisting stringified UploadFile(...) placeholders into DB.
            raw_value = str(payload.get(field_key, "")).strip()
            if raw_value.startswith("UploadFile("):
                payload.pop(field_key, None)

        cursor.execute(f"PRAGMA table_info({table_name})")
        allowed_cols = {str(row[1]) for row in cursor.fetchall()}
        insert_data = _map_payload_to_allowed_columns(payload, allowed_cols)
        if "record_date" in allowed_cols and "record_date" not in insert_data:
            insert_data["record_date"] = record_date

        if not insert_data:
            return {"success": False, "message": "无可写入字段"}
        columns = list(insert_data.keys())
        placeholders = ", ".join(["?"] * len(columns))
        sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"
        cursor.execute(sql, [insert_data[c] for c in columns])

        db_conn.commit()
        return {
            "success": True,
            "message": "记录已创建",
            "record_id": cursor.lastrowid,
            "form_page": form_page,
        }
    finally:
        db_conn.close()


@router.get("/{form_page}/{record_id}")
async def get_record(form_page: str, record_id: int, request: Request):
    await require_permission(request, "form", form_page, "read")
    db_conn = db_service.get_connection(thread_safe=False)
    cursor = db_conn.connection.cursor()
    try:
        table_name = _safe_form_table_name(form_page)
        cursor.execute(f"SELECT dr.* FROM {table_name} dr WHERE dr.id = ?", (record_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="记录不存在")
        data = dict(row)
        data["form_page"] = form_page
        data["image_list"] = _parse_images(data.get("images"))
        return data
    finally:
        db_conn.close()


@router.put("/{form_page}/{record_id}")
async def update_record(form_page: str, record_id: int, payload: dict[str, Any], request: Request):
    await require_permission(request, "form", form_page, "update")
    db_conn = db_service.get_connection(thread_safe=False)
    cursor = db_conn.connection.cursor()
    table_name = _safe_form_table_name(form_page)
    try:
        cursor.execute(f"PRAGMA table_info({table_name})")
        allowed_cols = {str(row[1]) for row in cursor.fetchall()}
        blocked = {"id", "created_at", "updated_at", "deleted", "deleted_at", "deleted_by"}
        mapped_payload = _map_payload_to_allowed_columns(payload, allowed_cols)
        update_data = {
            str(k): v for k, v in mapped_payload.items()
            if str(k) not in blocked
        }
        if not update_data:
            raise HTTPException(status_code=400, detail="没有可更新字段")

        set_sql = ", ".join([f"{k}=?" for k in update_data.keys()])
        params = [update_data[k] for k in update_data.keys()]
        if "updated_at" in allowed_cols:
            sql = f"UPDATE {table_name} SET {set_sql}, updated_at=CURRENT_TIMESTAMP WHERE id=?"
        else:
            sql = f"UPDATE {table_name} SET {set_sql} WHERE id=?"
        params.append(record_id)
        cursor.execute(sql, params)
        db_conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="记录不存在")
        return {"success": True, "message": "记录已更新"}
    finally:
        db_conn.close()


@router.post("/{form_page}/{record_id}/images")
async def update_record_images(form_page: str, record_id: int, request: Request):
    await require_permission(request, "form", form_page, "update")
    db_conn = db_service.get_connection(thread_safe=False)
    cursor = db_conn.connection.cursor()
    table_name = _safe_form_table_name(form_page)
    try:
        cursor.execute(f"SELECT * FROM {table_name} WHERE id = ?", (record_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="记录不存在")
        existing_record = dict(row)

        form = await request.form()
        keep_map: dict[str, list[str]] = {}
        for k, v in form.multi_items():
            key = str(k).strip()
            if not key:
                continue
            if _is_upload_file(v):
                continue
            if key.startswith("keep_"):
                field_key = key[5:]
                if not field_key:
                    continue
                try:
                    parsed = json.loads(str(v))
                except Exception:
                    parsed = []
                if isinstance(parsed, list):
                    keep_map[field_key] = [str(x).strip() for x in parsed if str(x).strip()]

        image_fields = [
            f for f in load_merged_fields_for_schema(form_page)
            if str(f.get("type", "")).strip() in {"image", "file"}
        ]
        changed_fields: dict[str, str] = {}
        next_index = 1
        for field in image_fields:
            field_key = str(field.get("key", "")).strip()
            if not field_key:
                continue
            old_list = _parse_images(existing_record.get(field_key))
            keep_list = keep_map.get(field_key, old_list)
            # Keep only valid /images urls.
            keep_list = [x for x in keep_list if _image_url_to_path(x) is not None]

            files = _extract_upload_files(form, field_key)
            new_urls = await _save_images_for_field(files, {"form_page": form_page, **existing_record}, field_key, next_index)
            next_index += len(new_urls)
            merged = keep_list + new_urls
            changed_fields[field_key] = json.dumps(merged, ensure_ascii=False)

            removed_urls = set(old_list) - set(keep_list)
            for removed in removed_urls:
                file_path = _image_url_to_path(removed)
                if file_path and file_path.exists():
                    try:
                        file_path.unlink()
                    except Exception:
                        pass

        if not changed_fields:
            return {"success": True, "message": "无图片字段需要更新"}

        set_sql = ", ".join([f"{k}=?" for k in changed_fields.keys()])
        params: list[Any] = [changed_fields[k] for k in changed_fields.keys()]
        cursor.execute(f"PRAGMA table_info({table_name})")
        cols = {str(r[1]) for r in cursor.fetchall()}
        if "updated_at" in cols:
            sql = f"UPDATE {table_name} SET {set_sql}, updated_at=CURRENT_TIMESTAMP WHERE id=?"
        else:
            sql = f"UPDATE {table_name} SET {set_sql} WHERE id=?"
        params.append(record_id)
        cursor.execute(sql, params)
        db_conn.commit()
        return {"success": True, "message": "图片已更新"}
    finally:
        db_conn.close()


@router.delete("/{form_page}/{record_id}")
async def delete_record(form_page: str, record_id: int, request: Request):
    await require_permission(request, "form", form_page, "delete")
    db_conn = db_service.get_connection(thread_safe=False)
    cursor = db_conn.connection.cursor()
    table_name = _safe_form_table_name(form_page)
    cursor.execute(f"DELETE FROM {table_name} WHERE id = ?", (record_id,))
    db_conn.commit()
    deleted = cursor.rowcount
    db_conn.close()

    if deleted == 0:
        raise HTTPException(status_code=404, detail="记录不存在")
    return {"success": True, "message": "记录已删除"}
