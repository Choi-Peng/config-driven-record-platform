"""
Version: 1.0
表单布局加载。
"""
from __future__ import annotations
from app.core.config import get_config_service

FIELD_TYPES = {"text", "number", "select", "textarea", "date", "time", "file", "image"}


def _normalize_layout(data: dict) -> dict:
    groups = data.get("groups")
    combine_datetime = bool(data.get("combine_datetime", False))
    if not isinstance(groups, dict):
        return {"groups": [], "combine_datetime": combine_datetime}

    normalized_groups: list[dict] = []

    for group_key, group in groups.items():
        if not isinstance(group, dict):
            continue

        ng = {
            "key": group_key,
            "title": str(group.get("title", group_key)).strip() or group_key,
            "icon": str(group.get("icon", "bi-ui-checks-grid")).strip() or "bi-ui-checks-grid",
            "refresh_after_upload": bool(group.get("refresh_after_upload", False)),
            "fields": [],
        }
        raw_fields = group.get("fields", [])
        if not isinstance(raw_fields, list):
            raw_fields = []

        for field in raw_fields:
            if not isinstance(field, dict):
                continue
            field_key = str(field.get("key", "")).strip()
            if not field_key:
                continue
            bf = {"key": field_key}
            ftype = str(field.get("type", "text")).strip()
            if ftype in FIELD_TYPES:
                bf["type"] = ftype
            else:
                bf["type"] = "text"
            bf["label"] = str(field.get("label", field_key)).strip() or field_key
            try:
                width = int(field.get("width", 12))
            except Exception:
                width = 12
            bf["width"] = min(12, max(1, width))
            if "required" in field:
                bf["required"] = bool(field["required"])
            if "step" in field:
                bf["step"] = str(field["step"])
            if "rows" in field:
                try:
                    bf["rows"] = max(1, int(field["rows"]))
                except Exception:
                    pass
            if "default" in field:
                bf["default"] = str(field["default"])
            if "placeholder" in field:
                bf["placeholder"] = str(field["placeholder"])
            if "accept" in field:
                bf["accept"] = str(field["accept"])
            elif bf["type"] == "image":
                bf["accept"] = "image/*"
            if "multiple" in field:
                bf["multiple"] = bool(field["multiple"])
            elif bf["type"] == "image":
                bf["multiple"] = True
            if bf["type"] == "select":
                bf["source"] = field.get("source", {})
            dep_raw = field.get("depends_on")
            if dep_raw:
                dep = str(dep_raw).strip()
                if dep:
                    bf["depends_on"] = dep
            ng["fields"].append(bf)

        normalized_groups.append(ng)

    return {"groups": normalized_groups, "combine_datetime": combine_datetime}


def load_form_layout(page_key: str) -> dict:
    config_service = get_config_service()
    main = config_service.get_main_config()
    form_name = page_key or main.active_form
    raw = config_service.get_form_config(form_name)
    layout = _normalize_layout(raw)
    layout["title"] = str(main.form_pages[form_name].title or "数据填报")
    return layout


def load_merged_fields_for_schema(page_key: str) -> list[dict]:
    """All normalized fields from every form page, first occurrence wins (same DB table)."""
    seen: set[str] = set()
    out: list[dict] = []
    layout = load_form_layout(page_key)
    for g in layout.get("groups") or []:
        for field in g.get("fields") or []:
            if not isinstance(field, dict):
                continue
            k = str(field.get("key", "")).strip()
            if not k or k in seen:
                continue
            seen.add(k)
            out.append(field)
    return out


if __name__ == "__main__":
    import json
    data = load_merged_fields_for_schema("greenhouse")
    print(json.dumps(data, ensure_ascii=False, indent=2))