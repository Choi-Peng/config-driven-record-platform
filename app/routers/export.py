import csv
import io
import re
import zipfile
from datetime import datetime
from io import StringIO
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response, StreamingResponse

from app.core.config import get_config_service
from app.core.database import get_database_service
from app.form_layout import load_merged_fields_for_schema
from app.tools.permission_checker import check_permission

router = APIRouter(prefix="/export", tags=["export"])
db_service = get_database_service()


def _safe_slug(value: str) -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", str(value or "").strip())
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "records"


def _parse_selected(selected_items: list[str]) -> dict[str, set[int]]:
    out: dict[str, set[int]] = {}
    for item in selected_items:
        text = str(item or "").strip()
        if ":" not in text:
            continue
        page_key, id_text = text.split(":", 1)
        page = page_key.strip()
        if not page:
            continue
        if not re.fullmatch(r"\d+", id_text.strip()):
            continue
        out.setdefault(page, set()).add(int(id_text.strip()))
    return out


def _form_field_label_map(form_key: str) -> dict[str, str]:
    labels: dict[str, str] = {}
    for field in load_merged_fields_for_schema(form_key):
        key = str(field.get("key", "")).strip()
        if not key:
            continue
        labels[key] = str(field.get("label", key)).strip() or key
    labels.setdefault("id", "编号")
    labels.setdefault("record_date", "日期")
    labels.setdefault("record_time", "时间")
    labels.setdefault("created_at", "创建时间")
    labels.setdefault("updated_at", "更新时间")
    return labels


def _table_columns(cursor, table_name: str) -> list[str]:
    cursor.execute(f"PRAGMA table_info({table_name})")
    return [str(row[1]) for row in cursor.fetchall() if str(row[1]).strip()]


def _table_exists(cursor, table_name: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table_name,),
    )
    return cursor.fetchone() is not None


def _csv_text(columns: list[str], labels: dict[str, str], rows: list[dict[str, Any]]) -> str:
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([labels.get(col, col) for col in columns])
    for row in rows:
        writer.writerow([row.get(col, "") for col in columns])
    return output.getvalue()


@router.get("/csv")
async def export_csv(
    request: Request,
    form_page: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    selected: list[str] = Query(default=[]),
):
    viewer = request.session.get("viewer") or {"role_name": "viewer"}
    role = str(viewer.get("role_name", "viewer"))
    db_conn = db_service.get_connection(thread_safe=False)
    cursor = db_conn.connection.cursor()
    try:
        selected_items = selected if isinstance(selected, list) else []
        selected_map = _parse_selected(selected_items)
        pages = list(get_config_service().get_main_config().form_pages.keys())
        if selected_map:
            target_pages = list(selected_map.keys())
            if form_page:
                target_pages = [p for p in target_pages if p == form_page]
        else:
            target_pages = [form_page] if form_page else pages
        target_pages = [p for p in target_pages if p in pages and check_permission(role, "form", p, "read")]
        files: dict[str, str] = {}

        for page_key in target_pages:
            table_name = f"records_{page_key}"
            if not _table_exists(cursor, table_name):
                continue
            columns = _table_columns(cursor, table_name)
            if not columns:
                continue
            export_columns = [c for c in columns if c not in {"deleted", "deleted_at", "deleted_by"}]
            if not export_columns:
                continue

            where_clauses = ["1=1"]
            params: list[Any] = []
            if start_date and "record_date" in columns:
                where_clauses.append("record_date >= ?")
                params.append(start_date)
            if end_date and "record_date" in columns:
                where_clauses.append("record_date <= ?")
                params.append(end_date)
            selected_ids = selected_map.get(page_key, set())
            if selected_ids:
                placeholders = ", ".join(["?"] * len(selected_ids))
                where_clauses.append(f"id IN ({placeholders})")
                params.extend(sorted(selected_ids))

            order_sql = " ORDER BY record_date DESC, id DESC" if "record_date" in columns else " ORDER BY id DESC"
            sql = f"SELECT {', '.join(export_columns)} FROM {table_name} WHERE {' AND '.join(where_clauses)}{order_sql}"
            cursor.execute(sql, params)
            rows = [dict(r) for r in cursor.fetchall()]
            labels = _form_field_label_map(page_key)
            files[page_key] = _csv_text(export_columns, labels, rows)

        if not files:
            empty_csv = _csv_text(["message"], {"message": "提示"}, [{"message": "无可导出数据"}]).encode("utf-8-sig")
            return StreamingResponse(
                iter([empty_csv]),
                media_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": "attachment; filename=records_empty.csv"},
            )

        if len(files) == 1:
            page_key = next(iter(files.keys()))
            payload = files[page_key].encode("utf-8-sig")
            filename = f"records_{_safe_slug(page_key)}.csv"
            return StreamingResponse(
                iter([payload]),
                media_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": f"attachment; filename={filename}"},
            )

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for page_key, csv_text in files.items():
                zf.writestr(f"records_{_safe_slug(page_key)}.csv", csv_text)
        zip_name = f"records_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        return Response(
            content=buffer.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={zip_name}"},
        )
    finally:
        db_conn.close()
