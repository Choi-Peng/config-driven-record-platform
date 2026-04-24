"""
页面模板上下文构建。

Version: 1.0.0
统一注入当前用户、站点信息与导航数据，并按权限过滤可见模块。
"""
from fastapi import Request
from app.core.config import get_config_service
from app.tools.permission_checker import check_permission


def _normalize_items(raw: object) -> list[dict]:
    if isinstance(raw, list):
        out = []
        for item in raw:
            if isinstance(item, dict):
                key = str(item.get("key", "")).strip()
                if key:
                    out.append(item)
        return out
    if isinstance(raw, dict):
        out = []
        for key, value in raw.items():
            k = str(key).strip()
            if not k:
                continue
            title = k
            icon = None
            if isinstance(value, dict):
                title = str(value.get("title", k)).strip() or k
                icon = value.get("icon")
            else:
                title = str(getattr(value, "title", k)).strip() or k
                icon = getattr(value, "icon", None)
            item = {"key": k, "title": title}
            if icon:
                item["icon"] = icon
            out.append(item)
        return out
    return []


def template_context(request: Request, tables: object | None = None, **extra):
    main = get_config_service().get_main_config()
    form_pages = _normalize_items(extra.pop("form_pages", None) or main.form_pages)
    managed_tables = _normalize_items(tables if tables is not None else main.tables)

    # 获取当前用户信息
    current_user = request.session.get("viewer")
    user_role = (current_user or {}).get("role_name", "viewer")
    # 表单页面始终可见；具体可编辑性由页面内 create 权限控制。
    managed_tables = [
        t for t in managed_tables
        if check_permission(user_role, "table", t["key"], "read")
    ]

    return {
        "request": request,
        "current_user": current_user,
        "user_role": user_role,
        "site_title": main.title,
        "form_pages": form_pages,
        "managed_tables": managed_tables,
        **extra,
    }
