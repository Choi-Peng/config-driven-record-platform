"""
选项API路由

提供动态选项加载
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from app.services.options_service import get_options_service, get_field_options

router = APIRouter(prefix="/api/options", tags=["options"])


@router.get("/field/{form_name}/{field_key}")
async def get_field_options_api(form_name: str, field_key: str):
    """
    获取表单字段的选项

    Args:
        form_name: 表单名称
        field_key: 字段key

    Returns:
        选项列表
    """
    try:
        options = await get_field_options(form_name, field_key)
        return {"options": options}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/source")
async def get_options_by_source(source_type: str, table: str = None, key: str = None):
    """
    根据source配置获取选项

    Args:
        source_type: 来源类型 (options/database)
        table: 数据库表名 (仅database类型需要)
        key: 字段名 (仅database类型需要)

    Returns:
        选项列表
    """
    try:
        service = get_options_service()

        # 构建source配置
        source_config = {"type": source_type}

        if source_type == "options":
            # 这里可以扩展支持不同的静态选项类型
            raise HTTPException(status_code=400, detail="静态选项需要通过具体字段API获取")
        elif source_type == "database":
            if not table or not key:
                raise HTTPException(status_code=400, detail="database类型需要table和key参数")

            source_config["values"] = {
                "table": table,
                "key": key,
            }
        else:
            raise HTTPException(status_code=400, detail=f"不支持的source类型: {source_type}")

        options = await service.get_options(source_config)
        return {"options": options}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tables")
async def get_table_options():
    """
    获取所有可用的表格选项

    Returns:
        表格列表，用于动态选择数据源
    """
    from app.core.config import get_config_service

    try:
        config_service = get_config_service()
        main_config = config_service.get_main_config()

        tables = []
        for table_key, table_config in main_config.tables.items():
            tables.append({
                "key": table_key,
                "title": table_config.title,
                "table_name": config_service.get_table_config(table_key).get("table_name", table_key)
            })

        return {"tables": tables}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))