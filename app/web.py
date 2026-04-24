"""
Web 资源与模板配置。

Version: 1.0.1
负责初始化模板引擎并挂载图片静态资源路由。
"""
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.core.config import get_config_service

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

templates = Jinja2Templates(directory=TEMPLATES_DIR)


def mount_static(app: FastAPI) -> None:
    img_dir = get_config_service().get_main_config().data_paths.images
    os.makedirs(img_dir, exist_ok=True)
    app.mount("/images", StaticFiles(directory=img_dir), name="data_images")
