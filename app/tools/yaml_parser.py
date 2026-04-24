"""
YAML 解析工具。

Version: 1.0.0
负责解析表单 YAML，并支持 `!include` 引用展开。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any

from ruamel.yaml import YAML


class YamlParser:
    INCLUDE_PATTERN = re.compile(
        r"^(?P<indent>\s*)(?P<key>[A-Za-z0-9_\-]+):\s*!include:\s*(?P<target>.+?)\s*$",
        re.MULTILINE,
    )

    def __init__(self) -> None:
        self.yaml = YAML(typ="safe")

    @staticmethod
    def _strip_quotes(value: str) -> str:
        text = value.strip()
        if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
            return text[1:-1]
        return text

    def _inline_includes(
        self, raw_text: str, current_file: Path, visited: set[Path]
    ) -> str:
        def replace_match(match: re.Match[str]) -> str:
            indent = match.group("indent")
            key = match.group("key")
            target_text = self._strip_quotes(match.group("target"))
            include_path = (current_file.parent / target_text).resolve()

            if include_path in visited:
                raise ValueError(f"Circular include detected: {include_path}")
            if not include_path.exists():
                raise FileNotFoundError(f"Include target does not exist: {include_path}")

            include_raw = include_path.read_text(encoding="utf-8")
            nested = self._inline_includes(include_raw, include_path, visited | {include_path})
            nested_lines = nested.splitlines()
            indented_nested = "\n".join(
                f"{indent}  {line}" if line else "" for line in nested_lines
            )
            return f"{indent}{key}:\n{indented_nested}"

        return self.INCLUDE_PATTERN.sub(replace_match, raw_text)

    def parse(self, yaml_file: Path) -> dict[str, Any]:
        yaml_file = yaml_file.resolve()
        raw = yaml_file.read_text(encoding="utf-8")
        expanded = self._inline_includes(raw, yaml_file, {yaml_file})
        data = self.yaml.load(expanded)
        if not isinstance(data, dict):
            raise TypeError(f"Expected mapping at root in {yaml_file}")
        return data

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse one form YAML file using ruamel.yaml with include inlining."
    )
    parser.add_argument(
        "yaml_file",
        help="Path to YAML file (e.g. config/forms/open_field.yaml)",
    )
    args = parser.parse_args()

    yaml_file_path = Path(args.yaml_file).resolve()
    parser_impl = YamlParser()
    yaml_data = parser_impl.parse(yaml_file_path)
    print(json.dumps(yaml_data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
