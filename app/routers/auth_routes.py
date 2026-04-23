from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from app.auth import hash_password, verify_user
from app.config import get_settings
from app.db import get_db
from app.page_ctx import template_context
from app.web import templates

router = APIRouter(tags=["auth"])


def _safe_next_url(raw: str | None) -> str:
    value = (raw or "").strip() or "/"
    if not value.startswith("/") or value.startswith("//"):
        return "/"
    return value


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    next_url = _safe_next_url(request.query_params.get("next", "/"))
    error = request.query_params.get("error")
    pending_bootstrap = request.session.get("pending_bootstrap_admin")
    bootstrap_required = bool(pending_bootstrap)
    bootstrap_username = str((pending_bootstrap or {}).get("username", "")).strip()
    return templates.TemplateResponse(
        "login.html",
        template_context(
            request,
            active_page="login",
            next_url=next_url,
            error=error,
            bootstrap_required=bootstrap_required,
            bootstrap_username=bootstrap_username,
        ),
    )


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    error = request.query_params.get("error")
    username = request.query_params.get("username", "")
    full_name = request.query_params.get("full_name", "")
    email = request.query_params.get("email", "")
    return templates.TemplateResponse(
        "register.html",
        template_context(
            request,
            active_page="register",
            error=error,
            username=username,
            full_name=full_name,
            email=email,
        ),
    )


@router.post("/register")
async def register_submit(
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    full_name: str = Form(""),
    email: str = Form(""),
):
    safe_username = username.strip()
    safe_full_name = full_name.strip()
    safe_email = email.strip()

    if len(safe_username) < 3:
        return RedirectResponse(
            url="/register?error=username&username=" + quote(safe_username, safe=""),
            status_code=302,
        )
    if len(password) < 6:
        q = (
            "?error=password"
            f"&username={quote(safe_username, safe='')}"
            f"&full_name={quote(safe_full_name, safe='')}"
            f"&email={quote(safe_email, safe='')}"
        )
        return RedirectResponse(
            url="/register" + q,
            status_code=302,
        )
    if password != confirm_password:
        q = (
            "?error=confirm"
            f"&username={quote(safe_username, safe='')}"
            f"&full_name={quote(safe_full_name, safe='')}"
            f"&email={quote(safe_email, safe='')}"
        )
        return RedirectResponse(
            url="/register" + q,
            status_code=302,
        )

    db = get_db()
    try:
        existing = db.execute(
            "SELECT id FROM users WHERE username = ? AND deleted = 0",
            (safe_username,),
        ).fetchone()
        if existing:
            q = (
                "?error=exists"
                f"&username={quote(safe_username, safe='')}"
                f"&full_name={quote(safe_full_name, safe='')}"
                f"&email={quote(safe_email, safe='')}"
            )
            return RedirectResponse(
                url="/register" + q,
                status_code=302,
            )

        role_row = db.execute(
            "SELECT id FROM roles WHERE name = 'viewer' AND deleted = 0 LIMIT 1"
        ).fetchone()
        role_id = role_row["id"] if role_row else 2

        db.execute(
            """
            INSERT INTO users (username, password_hash, role_id, full_name, email, status)
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (safe_username, hash_password(password), role_id, safe_full_name, safe_email),
        )
        db.commit()
    finally:
        db.close()

    return RedirectResponse(url="/login?next=/&registered=1", status_code=302)


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
):
    safe_next = _safe_next_url(next)
    safe_username = username.strip()

    viewer = await verify_user(safe_username, password)
    if not viewer:
        settings = get_settings()
        env_admin_username = str(settings.get("admin_username", "")).strip()
        env_admin_password = str(settings.get("admin_password", "")).strip()
        bootstrap_allowed = (
            bool(env_admin_password)
            and safe_username == env_admin_username
            and password == env_admin_password
        )
        if bootstrap_allowed:
            db = get_db()
            try:
                existing_user = db.execute(
                    "SELECT id FROM users WHERE username = ? AND deleted = 0 LIMIT 1",
                    (safe_username,),
                ).fetchone()
                if existing_user:
                    return RedirectResponse(
                        url="/login?error=credentials&next=" + quote(safe_next, safe=""),
                        status_code=302,
                    )
                admin_role = db.execute(
                    "SELECT id FROM roles WHERE name = 'admin' AND deleted = 0 LIMIT 1"
                ).fetchone()
                if not admin_role:
                    return RedirectResponse(
                        url="/login?error=config&next=" + quote(safe_next, safe=""),
                        status_code=302,
                    )
                request.session["pending_bootstrap_admin"] = {
                    "username": safe_username,
                    "role_id": int(admin_role["id"]),
                    "next": safe_next,
                }
                return RedirectResponse(
                    url="/login?bootstrap=1&next=" + quote(safe_next, safe=""),
                    status_code=302,
                )
            finally:
                db.close()
        return RedirectResponse(
            url="/login?error=credentials&next=" + quote(safe_next, safe=""), status_code=302
        )

    # 存储用户信息到session（排除敏感信息）
    request.session["viewer"] = {
        "id": viewer["id"],
        "username": viewer["username"],
        "role_id": viewer["role_id"],
        "role_name": viewer["role_name"],
        "full_name": viewer["full_name"],
        "email": viewer["email"]
    }

    request.session.pop("pending_bootstrap_admin", None)
    return RedirectResponse(url=safe_next, status_code=302)


@router.post("/login/bootstrap-admin")
async def bootstrap_admin_submit(
    request: Request,
    password: str = Form(...),
    confirm_password: str = Form(...),
):
    pending = request.session.get("pending_bootstrap_admin") or {}
    username = str(pending.get("username", "")).strip()
    role_id = pending.get("role_id")
    next_url = _safe_next_url(pending.get("next", "/"))
    if not username or role_id is None:
        return RedirectResponse(url="/login?error=credentials", status_code=302)

    if len(password) < 6:
        return RedirectResponse(
            url="/login?bootstrap=1&error=bootstrap_password&next=" + quote(next_url, safe=""),
            status_code=302,
        )
    if password != confirm_password:
        return RedirectResponse(
            url="/login?bootstrap=1&error=bootstrap_confirm&next=" + quote(next_url, safe=""),
            status_code=302,
        )

    db = get_db()
    try:
        existing = db.execute(
            "SELECT id FROM users WHERE username = ? LIMIT 1",
            (username,),
        ).fetchone()
        hashed = hash_password(password)
        if existing:
            db.execute(
                """
                UPDATE users
                SET password_hash = ?, role_id = ?, status = 1,
                    deleted = 0, deleted_at = NULL, deleted_by = NULL,
                    full_name = COALESCE(NULLIF(full_name, ''), '管理员')
                WHERE id = ?
                """,
                (hashed, int(role_id), int(existing["id"])),
            )
        else:
            db.execute(
                """
                INSERT INTO users (username, password_hash, role_id, full_name, status)
                VALUES (?, ?, ?, '管理员', 1)
                """,
                (username, hashed, int(role_id)),
            )
        db.commit()
    finally:
        db.close()

    viewer = await verify_user(username, password)
    if not viewer:
        return RedirectResponse(url="/login?error=config", status_code=302)

    request.session["viewer"] = {
        "id": viewer["id"],
        "username": viewer["username"],
        "role_id": viewer["role_id"],
        "role_name": viewer["role_name"],
        "full_name": viewer["full_name"],
        "email": viewer["email"]
    }
    request.session.pop("pending_bootstrap_admin", None)
    return RedirectResponse(url=next_url, status_code=302)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=302)


@router.get("/api/current-viewer")
async def get_current_user(request: Request):
    """获取当前用户信息"""
    viewer = request.session.get("viewer")
    if not viewer:
        raise HTTPException(status_code=401, detail="未登录")
    return viewer
