"""
核心基础设施模块

提供：
- 服务容器
- 依赖注入
- 生命周期管理
"""
from __future__ import annotations

from typing import Dict, Any, Type, Optional, Callable
from contextlib import contextmanager
import threading


class ServiceContainer:
    """服务容器（单例）"""

    _instance: Optional[ServiceContainer] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._services: Dict[str, Any] = {}
                cls._instance._factories: Dict[str, Callable] = {}
                cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._initialized = True

    def register(self, name: str, service: Any):
        """注册服务实例"""
        with self._lock:
            self._services[name] = service

    def register_factory(self, name: str, factory: Callable):
        """注册服务工厂"""
        with self._lock:
            self._factories[name] = factory

    def get(self, name: str) -> Any:
        """获取服务"""
        with self._lock:
            # 首先检查是否有实例
            if name in self._services:
                return self._services[name]

            # 检查是否有工厂
            if name in self._factories:
                service = self._factories[name]()
                self._services[name] = service
                return service

            raise KeyError(f"服务未注册: {name}")

    def has(self, name: str) -> bool:
        """检查服务是否存在"""
        with self._lock:
            return name in self._services or name in self._factories

    def remove(self, name: str):
        """移除服务"""
        with self._lock:
            if name in self._services:
                del self._services[name]
            if name in self._factories:
                del self._factories[name]

    def clear(self):
        """清空所有服务"""
        with self._lock:
            self._services.clear()
            self._factories.clear()

    @contextmanager
    def scoped(self, name: str, service: Any):
        """创建作用域内的服务"""
        old_service = None
        service_exists = self.has(name)

        if service_exists:
            old_service = self._services.get(name)

        self.register(name, service)

        try:
            yield service
        finally:
            if old_service is not None:
                self.register(name, old_service)
            elif service_exists:
                self.remove(name)


# 全局服务容器
_container: Optional[ServiceContainer] = None


def get_container() -> ServiceContainer:
    """获取全局服务容器"""
    global _container
    if _container is None:
        _container = ServiceContainer()
    return _container


def register_service(name: str, service: Any):
    """注册服务（便捷函数）"""
    get_container().register(name, service)


def register_factory(name: str, factory: Callable):
    """注册服务工厂（便捷函数）"""
    get_container().register_factory(name, factory)


def get_service(name: str) -> Any:
    """获取服务（便捷函数）"""
    return get_container().get(name)


def has_service(name: str) -> bool:
    """检查服务是否存在（便捷函数）"""
    return get_container().has(name)