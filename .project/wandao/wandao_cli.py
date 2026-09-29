#!/usr/bin/env python3
"""Small CLI helpers shared by Wandao provider scripts."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from typing import Any


def read_id_file(file_path: str | Path) -> list[str]:
    path = Path(file_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"ID 文件不存在：{path}")
    text = path.read_text(encoding="utf-8")
    values: Any
    try:
        values = json.loads(text)
    except json.JSONDecodeError:
        values = [line.strip() for line in text.splitlines() if line.strip()]
    if isinstance(values, dict):
        values = values.get("docIds") or values.get("doc_ids") or values.get("ids") or []
    if not isinstance(values, list):
        raise ValueError("ID 文件必须是 JSON 数组、包含 docIds/doc_ids/ids 的对象，或逐行文本。")
    return [str(item).strip() for item in values if str(item).strip()]


def extend_arg_list_from_file(args: Namespace, attr: str = "selected_doc_ids", file_attr: str = "doc_id_file") -> None:
    file_path = str(getattr(args, file_attr, "") or "").strip()
    if not file_path:
        return
    current = getattr(args, attr, None)
    if current is None:
        current = []
        setattr(args, attr, current)
    current.extend(read_id_file(file_path))
