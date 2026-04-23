"""
数据库服务

提供数据库连接管理和操作
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from contextlib import contextmanager

from .exceptions import DatabaseError, ConfigError
from . import get_container, register_service
from .config import get_config_service


class DatabaseConnection:
    """数据库连接包装器"""

    def __init__(self, connection: sqlite3.Connection, in_transaction: bool = False):
        self.connection = connection
        self.in_transaction = in_transaction
        self._lock = threading.Lock()

    def execute(self, sql: str, params: Tuple = ()) -> sqlite3.Cursor:
        """执行SQL语句"""
        try:
            with self._lock:
                return self.connection.execute(sql, params)
        except sqlite3.Error as e:
            raise DatabaseError(f"执行SQL失败: {e}", sql=sql, params=params)

    def executemany(self, sql: str, params_list: List[Tuple]) -> sqlite3.Cursor:
        """批量执行SQL语句"""
        try:
            with self._lock:
                return self.connection.executemany(sql, params_list)
        except sqlite3.Error as e:
            raise DatabaseError(f"批量执行SQL失败: {e}", sql=sql, params=params_list)

    def executescript(self, sql_script: str) -> sqlite3.Cursor:
        """执行SQL脚本"""
        try:
            with self._lock:
                return self.connection.executescript(sql_script)
        except sqlite3.Error as e:
            raise DatabaseError(f"执行SQL脚本失败: {e}", sql=sql_script)

    def commit(self):
        """提交事务"""
        try:
            with self._lock:
                self.connection.commit()
        except sqlite3.Error as e:
            raise DatabaseError(f"提交事务失败: {e}")

    def rollback(self):
        """回滚事务"""
        try:
            with self._lock:
                self.connection.rollback()
        except sqlite3.Error as e:
            raise DatabaseError(f"回滚事务失败: {e}")

    def close(self):
        """关闭连接"""
        try:
            with self._lock:
                self.connection.close()
        except sqlite3.Error as e:
            raise DatabaseError(f"关闭连接失败: {e}")


class DatabaseService:
    """数据库服务"""

    def __init__(self):
        self.config_service = get_config_service()
        self._connection_pool: Dict[int, DatabaseConnection] = {}
        self._pool_lock = threading.Lock()
        self._initialized = False

    def _get_database_path(self) -> str:
        """获取数据库路径"""
        config = self.config_service.get_main_config()
        return config.data_paths.database

    def _apply_database_config(self, conn: sqlite3.Connection):
        """应用数据库配置"""
        config = self.config_service.get_main_config()
        db_config = config.database_config

        cursor = conn.cursor()
        try:
            # 应用PRAGMA设置
            cursor.execute(f"PRAGMA journal_mode = {db_config.journal_mode}")
            cursor.execute(f"PRAGMA synchronous = {db_config.synchronous}")
            cursor.execute(f"PRAGMA foreign_keys = {'ON' if db_config.foreign_keys else 'OFF'}")
            cursor.execute(f"PRAGMA busy_timeout = {db_config.busy_timeout}")
            cursor.execute(f"PRAGMA cache_size = {db_config.cache_size}")
            cursor.execute(f"PRAGMA temp_store = {db_config.temp_store}")
            cursor.execute(f"PRAGMA mmap_size = {db_config.mmap_size}")
            conn.commit()
        except sqlite3.Error as e:
            raise DatabaseError(f"应用数据库配置失败: {e}")

    def _create_connection(self) -> DatabaseConnection:
        """创建新的数据库连接"""
        db_path = self._get_database_path()

        # 确保数据库目录存在
        db_dir = Path(db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 创建连接
            conn = sqlite3.connect(db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row

            # 应用配置
            self._apply_database_config(conn)

            return DatabaseConnection(conn)
        except sqlite3.Error as e:
            raise DatabaseError(f"创建数据库连接失败: {e}", details={"db_path": db_path})

    def get_connection(self, thread_safe: bool = True) -> DatabaseConnection:
        """
        获取数据库连接

        Args:
            thread_safe: 是否线程安全（为每个线程创建独立连接）

        Returns:
            DatabaseConnection: 数据库连接
        """
        if not thread_safe:
            return self._create_connection()

        # 线程安全模式：为每个线程提供独立连接
        thread_id = threading.get_ident()

        with self._pool_lock:
            if thread_id not in self._connection_pool:
                self._connection_pool[thread_id] = self._create_connection()

            return self._connection_pool[thread_id]

    def close_all_connections(self):
        """关闭所有连接"""
        with self._pool_lock:
            for thread_id, connection in list(self._connection_pool.items()):
                try:
                    connection.close()
                except Exception as e:
                    # 记录错误但不中断
                    print(f"关闭连接失败 (线程 {thread_id}): {e}")
                finally:
                    del self._connection_pool[thread_id]

    @contextmanager
    def connection(self, thread_safe: bool = True):
        """
        数据库连接上下文管理器

        Args:
            thread_safe: 是否线程安全

        Yields:
            DatabaseConnection: 数据库连接
        """
        conn = self.get_connection(thread_safe)
        try:
            yield conn
        finally:
            # 在线程安全模式下，连接由连接池管理，不在这里关闭
            if not thread_safe:
                conn.close()

    @contextmanager
    def transaction(self, thread_safe: bool = True):
        """
        事务上下文管理器

        Args:
            thread_safe: 是否线程安全

        Yields:
            DatabaseConnection: 数据库连接（在事务中）
        """
        conn = self.get_connection(thread_safe)
        conn.in_transaction = True

        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.in_transaction = False
            # 在线程安全模式下，连接由连接池管理，不在这里关闭
            if not thread_safe:
                conn.close()

    def execute(self, sql: str, params: Tuple = (), thread_safe: bool = True) -> sqlite3.Cursor:
        """执行SQL语句"""
        with self.connection(thread_safe) as conn:
            return conn.execute(sql, params)

    def executemany(self, sql: str, params_list: List[Tuple], thread_safe: bool = True) -> sqlite3.Cursor:
        """批量执行SQL语句"""
        with self.connection(thread_safe) as conn:
            return conn.executemany(sql, params_list)

    def fetchone(self, sql: str, params: Tuple = (), thread_safe: bool = True) -> Optional[Dict[str, Any]]:
        """查询单条记录"""
        with self.connection(thread_safe) as conn:
            cursor = conn.execute(sql, params)
            row = cursor.fetchone()
            return dict(row) if row else None

    def fetchall(self, sql: str, params: Tuple = (), thread_safe: bool = True) -> List[Dict[str, Any]]:
        """查询所有记录"""
        with self.connection(thread_safe) as conn:
            cursor = conn.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]

    def table_exists(self, table_name: str, thread_safe: bool = True) -> bool:
        """检查表是否存在"""
        sql = """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name=?
        """
        result = self.fetchone(sql, (table_name,), thread_safe)
        return result is not None

    def get_table_info(self, table_name: str, thread_safe: bool = True) -> List[Dict[str, Any]]:
        """获取表结构信息"""
        sql = f"PRAGMA table_info({table_name})"
        return self.fetchall(sql, thread_safe=thread_safe)

    def initialize_database(self):
        """初始化数据库（创建表等）"""
        if self._initialized:
            return

        try:
            # 这里可以添加数据库初始化逻辑
            # 例如：创建必要的表、索引等
            self._initialized = True
        except Exception as e:
            raise DatabaseError(f"初始化数据库失败: {e}")

    def get_database_info(self) -> Dict[str, Any]:
        """获取数据库信息"""
        try:
            with self.connection() as conn:
                cursor = conn.execute("SELECT sqlite_version()")
                version = cursor.fetchone()[0]

                cursor = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
                table_count = cursor.fetchone()[0]

                return {
                    "path": self._get_database_path(),
                    "sqlite_version": version,
                    "table_count": table_count,
                    "connection_pool_size": len(self._connection_pool),
                    "initialized": self._initialized,
                }
        except Exception as e:
            raise DatabaseError(f"获取数据库信息失败: {e}")


# 创建并注册数据库服务
def create_database_service() -> DatabaseService:
    """创建数据库服务"""
    return DatabaseService()


# 注册到服务容器
database_service = create_database_service()
register_service("database", database_service)


# 便捷函数
def get_database_service() -> DatabaseService:
    """获取数据库服务"""
    return get_container().get("database")


@contextmanager
def db_connection(thread_safe: bool = True):
    """数据库连接上下文管理器（便捷函数）"""
    service = get_database_service()
    with service.connection(thread_safe) as conn:
        yield conn


@contextmanager
def db_transaction(thread_safe: bool = True):
    """事务上下文管理器（便捷函数）"""
    service = get_database_service()
    with service.transaction(thread_safe) as conn:
        yield conn


def db_execute(sql: str, params: Tuple = (), thread_safe: bool = True) -> sqlite3.Cursor:
    """执行SQL语句（便捷函数）"""
    service = get_database_service()
    return service.execute(sql, params, thread_safe)


def db_fetchone(sql: str, params: Tuple = (), thread_safe: bool = True) -> Optional[Dict[str, Any]]:
    """查询单条记录（便捷函数）"""
    service = get_database_service()
    return service.fetchone(sql, params, thread_safe)


def db_fetchall(sql: str, params: Tuple = (), thread_safe: bool = True) -> List[Dict[str, Any]]:
    """查询所有记录（便捷函数）"""
    service = get_database_service()
    return service.fetchall(sql, params, thread_safe)


if __name__ == "__main__":
    # 测试数据库服务
    service = get_database_service()

    print("数据库服务测试:")
    print(f"数据库路径: {service._get_database_path()}")

    # 测试连接
    with service.connection() as conn:
        cursor = conn.execute("SELECT sqlite_version()")
        version = cursor.fetchone()[0]
        print(f"SQLite版本: {version}")

    # 测试事务
    try:
        with service.transaction() as conn:
            # 测试表是否存在
            table_exists = service.table_exists("test_table")
            print(f"测试表是否存在: {table_exists}")
    except Exception as e:
        print(f"事务测试失败: {e}")

    # 获取数据库信息
    info = service.get_database_info()
    print("\n数据库信息:")
    for key, value in info.items():
        print(f"  {key}: {value}")