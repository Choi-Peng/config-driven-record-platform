"""
表单配置加载器

加载和管理表单配置文件 (config/forms/*.yaml)
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Any
from . import get_config_manager


class FormConfigLoader:
    """表单配置加载器"""

    def __init__(self):
        self.config_manager = get_config_manager()

    def load(self, path: str | Path) -> Dict[str, Any]:
        """
        加载表单配置

        Args:
            path: 表单配置文件路径

        Returns:
            dict: 表单配置数据
        """
        path_obj = Path(path)
        if path_obj.is_absolute():
            path = path_obj.resolve()
        else:
            path = self.config_manager.resolve_config_file(str(path_obj))

        # 检查缓存
        cache_key = self.config_manager._get_cache_key("form", str(path))
        if self.config_manager._is_cache_valid(cache_key, str(path)):
            return self.config_manager._config_cache[cache_key]

        # 读取配置文件
        data = self.config_manager._read_yaml(path)

        # 构建结果
        result = {
            "version": data.get("version", ""),
            "title": data.get("title", ""),
            "icon": data.get("icon", "bi-ui-checks-grid"),
            "combine_datetime": data.get("combine_datetime"),
            "groups": data.get("groups", {}),
            "show_columns": data.get("show_columns", []),
            "order": data.get("order", {}),
            "permissions": data.get("permissions", {}),
        }

        # 更新缓存
        self.config_manager._update_cache(cache_key, str(path), result)

        return result

    def load_by_name(self, form_name: str, forms_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        通过表单名称加载配置

        Args:
            form_name: 表单名称
            forms_config: 表单配置字典（来自主配置）

        Returns:
            dict: 表单配置数据
        """
        if form_name not in forms_config:
            raise ValueError(f"表单 '{form_name}' 不存在")

        form_info = forms_config[form_name]
        form_file = form_info.get("file")

        if not form_file:
            raise ValueError(f"表单 '{form_name}' 没有配置文件路径")

        return self.load(form_file)


# 全局表单配置加载器实例
_form_config_loader: FormConfigLoader = None


def get_form_config_loader() -> FormConfigLoader:
    """获取表单配置加载器实例"""
    global _form_config_loader
    if _form_config_loader is None:
        _form_config_loader = FormConfigLoader()
    return _form_config_loader


def load_form_config(path: str | Path) -> Dict[str, Any]:
    """加载表单配置（便捷函数）"""
    loader = get_form_config_loader()
    return loader.load(path)


def load_form_config_by_name(form_name: str, forms_config: Dict[str, Any]) -> Dict[str, Any]:
    """通过表单名称加载配置（便捷函数）"""
    loader = get_form_config_loader()
    return loader.load_by_name(form_name, forms_config)


if __name__ == "__main__":
    import json

    # 测试表单配置加载
    test_path = "/Users/choi/好时吉/记录系统/config/forms/open_field.yaml"
    config = load_form_config(test_path)
    print(json.dumps(config, ensure_ascii=False, indent=2))

    # 测试缓存
    print("\n第二次加载（应该从缓存读取）:")
    config2 = load_form_config(test_path)
    print(f"配置相同: {config == config2}")

    # 测试缓存信息
    print("\n缓存信息:")
    print(json.dumps(get_config_manager().get_cache_info(), ensure_ascii=False, indent=2))