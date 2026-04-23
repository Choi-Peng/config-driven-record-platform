"""用户认证与会话管理。"""

import secrets
import bcrypt
from typing import Dict, Optional

from fastapi import HTTPException, Request
from app.config import get_settings
from app.db import get_db
from app.tools.permission_checker import check_permission


def hash_password(password: str) -> str:
    """使用bcrypt哈希密码"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode(), salt).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    try:
        return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())
    except Exception:
        return False


async def verify_user(username: str, password: str) -> Optional[Dict]:
    """验证用户凭据并返回用户信息"""
    db = get_db()

    try:
        # 查询用户信息，包括角色名称
        cursor = db.execute("""
            SELECT u.id, u.username, u.password_hash, u.role_id, u.full_name,
                   u.email, u.status, r.name as role_name
            FROM users u
            LEFT JOIN roles r ON u.role_id = r.id
            WHERE u.username = ? AND u.deleted = 0
        """, (username,))

        viewer = cursor.fetchone()
        if not viewer:
            return None

        # 检查用户状态
        if viewer["status"] != 1:
            return None

        # 验证密码
        if not verify_password(password, viewer["password_hash"]):
            return None

        return dict(viewer)
    except Exception as e:
        print(f"用户验证错误: {e}")
        return None


async def require_auth(request: Request, required_role: Optional[str] = None) -> Dict:
    """要求用户认证，可选检查特定角色"""
    viewer = request.session.get("viewer") or {"role_name": "viewer"}

    if required_role and viewer.get("role_name") != required_role:
        raise HTTPException(status_code=403, detail="权限不足")

    return viewer


async def require_permission(request: Request, resource_type: str, resource_name: str, action: str) -> Dict:
    """要求用户有特定资源的权限"""
    viewer = request.session.get("viewer") or {"role_name": "viewer"}
    has_perm = check_permission(
        role=viewer.get("role_name", "viewer"),
        resource_type=resource_type,
        resource_name=resource_name,
        action=action
    )
    if not has_perm:
        raise HTTPException(status_code=403, detail="权限不足")
    return viewer
