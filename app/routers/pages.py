"""
页面渲染路由。

Version: 1.0.0
负责表单页、记录页、管理页等模板渲染，并在入口层做访问权限守卫。
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from app.core.config import get_config_service
from app.form_layout import load_form_layout
from app.page_ctx import template_context
from app.tools.permission_checker import check_permission
from app.web import templates

router = APIRouter()


def _main():
    return get_config_service().get_main_config()


def _guard_page(request: Request, path: str, resource_type: str = None, resource_name: str = None, action: str = "read"):
    """检查页面访问权限"""
    viewer = request.session.get("viewer") or {"role_name": "viewer"}

    # 如果有资源权限要求，检查权限
    if resource_type and resource_name:
        has_perm = check_permission(
            role=viewer.get("role_name", "viewer"),
            resource_type=resource_type,
            resource_name=resource_name,
            action=action,
        )
        if not has_perm:
            return RedirectResponse(url="/", status_code=302)

    return None


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return RedirectResponse(
        url=f"/form/{_main().active_form}",
        status_code=302,
    )


@router.get("/form/{page_key}", response_class=HTMLResponse)
async def form_page(request: Request, page_key: str):
    if (r := _guard_page(request, f"/form/{page_key}")) is not None:
        return r
    main = _main()
    fp = get_config_service().get_form_config(page_key)
    viewer = request.session.get("viewer") or {}
    role = viewer.get("role_name", "viewer")
    can_create_form = check_permission(role, "form", page_key, "create")
    return templates.TemplateResponse(
        "index.html",
        template_context(
            request,
            tables=main.tables,
            active_page="entry",
            form_pages=main.form_pages,
            current_form_page=page_key,
            form_page_title=fp.get("title") or page_key,
            can_create_form=can_create_form,
        ),
    )


@router.get("/records", response_class=HTMLResponse)
async def records_page(request: Request):
    if (r := _guard_page(request, "/records")) is not None:
        return r
    main = _main()
    return templates.TemplateResponse(
        "records.html",
        template_context(
            request,
            tables=main.tables,
            active_page="records",
            form_pages=main.form_pages,
            current_form_page=None,
        ),
    )


@router.get("/record/{form_page}/{record_id}", response_class=HTMLResponse)
async def record_detail_page(request: Request, form_page: str, record_id: int):
    if (r := _guard_page(request, f"/record/{form_page}/{record_id}", "form", form_page, "read")) is not None:
        return r
    viewer = request.session.get("viewer") or {}
    role = viewer.get("role_name", "viewer")
    can_update = check_permission(role, "form", form_page, "update")
    can_delete = check_permission(role, "form", form_page, "delete")
    main = _main()
    fp = get_config_service().get_form_config(form_page)
    return templates.TemplateResponse(
        "record_detail.html",
        template_context(
            request,
            tables=main.tables,
            active_page="records",
            form_pages=main.form_pages,
            current_form_page=form_page,
            form_page_title=fp.get("title") or form_page,
            record_id=record_id,
            can_update=can_update,
            can_delete=can_delete,
        ),
    )


@router.get("/api/form-layout")
async def form_layout_config(page: str | None = None):
    return load_form_layout(page)


@router.get("/api/form-pages")
async def form_pages_config():
    pages = [{"key": key, "title": cfg.title, "file": cfg.file} for key, cfg in _main().form_pages.items()]
    return {"pages": pages}


@router.get("/api/options/crops")
async def crop_options():
    return get_config_service().get_table_config("crops")["seed_data"]


@router.get("/manage/fields", response_class=HTMLResponse)
async def manage_fields_page(request: Request):
    target = next(iter(_main().tables.keys()), "records")
    if (r := _guard_page(request, f"/manage/{target}", "table", target, "read")) is not None:
        return r
    return RedirectResponse(url=f"/manage/{target}", status_code=302)


def _table_exists(table_key: str) -> bool:
    return table_key in _main().tables


@router.get("/manage/{table_key}", response_class=HTMLResponse)
async def manage_table_page(request: Request, table_key: str):
    if not _table_exists(table_key):
        return RedirectResponse(url="/records", status_code=302)
    if (r := _guard_page(request, f"/manage/{table_key}", "table", table_key, "read")) is not None:
        return r
    return templates.TemplateResponse(
        "entity_list.html",
        template_context(
            request,
            tables=_main().tables,  # 传递tables参数
            active_page=f"manage_{table_key}",
            form_pages=_main().form_pages,
            current_form_page=None,
            table_key=table_key,
            table_title=_main().tables[table_key].title,
        ),
    )


@router.get("/manage/{table_key}/new", response_class=HTMLResponse)
async def manage_table_create_page(request: Request, table_key: str):
    if not _table_exists(table_key):
        return RedirectResponse(url="/records", status_code=302)
    if (r := _guard_page(request, f"/manage/{table_key}/new", "table", table_key, "create")) is not None:
        return r
    return templates.TemplateResponse(
        "entity_create.html",
        template_context(
            request,
            tables=_main().tables,  # 传递tables参数
            active_page=f"manage_{table_key}",
            form_pages=_main().form_pages,
            current_form_page=None,
            table_key=table_key,
            table_title=_main().tables[table_key].title,
        ),
    )
