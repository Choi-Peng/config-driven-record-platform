"""
异常定义

定义项目中的自定义异常
"""
from __future__ import annotations

from typing import Optional, Any


class AppError(Exception):
    """应用基础异常"""

    def __init__(self, message: str, code: str = "INTERNAL_ERROR", details: Optional[Any] = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details


class ConfigError(AppError):
    """配置错误"""

    def __init__(self, message: str, config_path: Optional[str] = None, details: Optional[Any] = None):
        super().__init__(message, "CONFIG_ERROR", details)
        self.config_path = config_path


class DatabaseError(AppError):
    """数据库错误"""

    def __init__(self, message: str, sql: Optional[str] = None, params: Optional[Any] = None, details: Optional[Any] = None):
        super().__init__(message, "DATABASE_ERROR", details)
        self.sql = sql
        self.params = params


class ValidationError(AppError):
    """验证错误"""

    def __init__(self, message: str, field: Optional[str] = None, value: Optional[Any] = None, details: Optional[Any] = None):
        super().__init__(message, "VALIDATION_ERROR", details)
        self.field = field
        self.value = value


class PermissionError(AppError):
    """权限错误"""

    def __init__(self, message: str, resource: Optional[str] = None, action: Optional[str] = None, role: Optional[str] = None, details: Optional[Any] = None):
        super().__init__(message, "PERMISSION_ERROR", details)
        self.resource = resource
        self.action = action
        self.role = role


class NotFoundError(AppError):
    """未找到错误"""

    def __init__(self, message: str, resource_type: Optional[str] = None, resource_id: Optional[Any] = None, details: Optional[Any] = None):
        super().__init__(message, "NOT_FOUND", details)
        self.resource_type = resource_type
        self.resource_id = resource_id


class BusinessError(AppError):
    """业务逻辑错误"""

    def __init__(self, message: str, business_code: str = "BUSINESS_ERROR", details: Optional[Any] = None):
        super().__init__(message, business_code, details)


# HTTP异常包装
class HTTPError(AppError):
    """HTTP错误"""

    def __init__(self, message: str, status_code: int = 500, code: str = "HTTP_ERROR", details: Optional[Any] = None):
        super().__init__(message, code, details)
        self.status_code = status_code


class BadRequestError(HTTPError):
    """400 Bad Request"""

    def __init__(self, message: str = "请求参数错误", details: Optional[Any] = None):
        super().__init__(message, 400, "BAD_REQUEST", details)


class UnauthorizedError(HTTPError):
    """401 Unauthorized"""

    def __init__(self, message: str = "未授权访问", details: Optional[Any] = None):
        super().__init__(message, 401, "UNAUTHORIZED", details)


class ForbiddenError(HTTPError):
    """403 Forbidden"""

    def __init__(self, message: str = "禁止访问", details: Optional[Any] = None):
        super().__init__(message, 403, "FORBIDDEN", details)


class NotFoundHTTPError(HTTPError):
    """404 Not Found"""

    def __init__(self, message: str = "资源未找到", details: Optional[Any] = None):
        super().__init__(message, 404, "NOT_FOUND", details)


class ConflictError(HTTPError):
    """409 Conflict"""

    def __init__(self, message: str = "资源冲突", details: Optional[Any] = None):
        super().__init__(message, 409, "CONFLICT", details)


class InternalServerError(HTTPError):
    """500 Internal Server Error"""

    def __init__(self, message: str = "服务器内部错误", details: Optional[Any] = None):
        super().__init__(message, 500, "INTERNAL_SERVER_ERROR", details)