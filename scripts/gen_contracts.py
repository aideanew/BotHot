#!/usr/bin/env python3
"""
gen_contracts.py — 从后端真实代码生成 TypeScript 契约 DTO（审查者重写版）

数据来源（两类，均可从仓库本身确定性推导，天然幂等）：
1. SQLAlchemy 模型内省：bothot_entities 的实体列名/类型/可空性 → interface
2. OpenAPI 请求模型：create_app().openapi() 的 components.schemas（Pydantic 请求体）

用法：
    python scripts/gen_contracts.py           # 生成/覆盖 packages/contracts/src/<域>/dto.ts
    python scripts/gen_contracts.py --check   # 幂等校验（CI）：重新生成与磁盘 diff，不一致退出 1

注意：
- 生成物带「请勿手动修改」头——手工编辑 dto.ts 会在 --check 下失败
- 分页双口径是冻结契约：bot/hot=page/page_size，knowledge/订阅/任务=limit/offset
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "apps" / "api"
CONTRACTS_DIR = PROJECT_ROOT / "packages" / "contracts" / "src"

# 域 → (模型模块, SQLAlchemy 实体)
DOMAIN_ENTITIES: dict[str, tuple[str, list[str]]] = {
    "bot": ("bothot_entities", ["BotChannel", "PushTask", "PushLog"]),
    "hot": ("bothot_entities", ["HotTopic", "HotTopicArticle", "DailyReport", "FeedItem"]),
    "push_event": ("bothot_entities", ["PushEvent"]),
    "knowledge": ("entities", ["KnowledgeSpace"]),
    "subscription": ("entities", ["Source", "SourceSubscription"]),
    "ingest": ("entities", ["Job", "JobItem"]),
}

# 域 → OpenAPI components.schemas 中的请求模型（Pydantic 请求体）
DOMAIN_REQUEST_SCHEMAS: dict[str, list[str]] = {
    "bot": ["ChannelCreateRequest", "ChannelUpdateRequest", "PushTaskCreateRequest", "PushTaskUpdateRequest"],
}

# SQLAlchemy 列类型 → TS 类型
_TS_TYPE_MAP: dict[str, str] = {
    "String": "string",
    "Text": "string",
    "Integer": "number",
    "SmallInteger": "number",
    "BigInteger": "number",
    "Float": "number",
    "Numeric": "number",
    "Boolean": "boolean",
    "DateTime": "string",
    "Date": "string",
    "JSON": "unknown",
}


def _load_models(module_name: str) -> dict[str, Any]:
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    import importlib

    m = importlib.import_module(f"app.models.{module_name}")
    out: dict[str, Any] = {}
    for name in dir(m):
        obj = getattr(m, name)
        if isinstance(obj, type) and issubclass(obj, m.Base) and obj is not m.Base:
            out[name] = obj
    return out


def _entity_to_ts(name: str, model: Any) -> str:
    lines = [f"export interface {name} {{"]
    for col in model.__table__.columns:
        py_type = type(col.type).__name__
        ts = _TS_TYPE_MAP.get(py_type, "unknown")
        nullable = bool(col.nullable)
        lines.append(f"  {col.name}: {ts}{' | null' if nullable else ''};")
    lines.append("}")
    return "\n".join(lines)


def _schema_to_ts(name: str, schema: dict[str, Any]) -> str:
    """OpenAPI components.schemas（Pydantic 请求模型）→ interface。"""
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    lines = [f"export interface {name} {{"]
    for prop, spec in props.items():
        ts = {"string": "string", "integer": "number", "number": "number", "boolean": "boolean"}.get(
            str(spec.get("type")), "unknown"
        )
        optional = prop not in required
        lines.append(f"  {prop}: {ts}{' | null' if optional else ''};")
    lines.append("}")
    return "\n".join(lines)


def _render_domain(domain: str, blocks: list[str], source_note: str) -> str:
    header = (
        "/**\n"
        f" * {domain} 域 — 契约 DTO\n"
        " *\n"
        " * 由 scripts/gen_contracts.py 自动生成，请勿手动修改（--check 幂等门禁）\n"
        f" * 源：{source_note}\n"
        " */\n\n"
    )
    return header + "\n\n".join(blocks) + "\n"


def generate() -> dict[str, str]:
    """返回 {域名: 文件内容}。"""
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    out: dict[str, str] = {}
    _model_cache: dict[str, dict[str, Any]] = {}

    for domain, (module_name, entity_names) in DOMAIN_ENTITIES.items():
        if module_name not in _model_cache:
            _model_cache[module_name] = _load_models(module_name)
        models = _model_cache[module_name]
        blocks = []
        for name in entity_names:
            if name not in models:
                raise SystemExit(f"[error] 模型 {name} 不存在于 app.models.{module_name}（域 {domain} 配置错误）")
            blocks.append(_entity_to_ts(name, models[name]))
        note = f"apps/api/app/models/{module_name}.py（SQLAlchemy 模型内省）"
        out[domain] = _render_domain(domain, blocks, note)

    # OpenAPI 请求模型（Pydantic 请求体）
    from app.main import create_app

    schema = create_app().openapi()
    components = schema.get("components", {}).get("schemas", {})
    for domain, wanted in DOMAIN_REQUEST_SCHEMAS.items():
        missing = [name for name in wanted if name not in components]
        if missing:
            raise SystemExit(f"[error] OpenAPI 缺少请求模型: {missing}（域 {domain}）")
        blocks = [_schema_to_ts(name, components[name]) for name in wanted]
        note = "apps/api/app/main.py create_app().openapi()（Pydantic 请求模型）"
        request_block = _render_domain(domain + " 请求", blocks, note).split("\n", 5)[-1]
        out[domain] = out[domain].rstrip("\n") + "\n\n" + request_block
    return out


def write_all(contents: dict[str, str]) -> None:
    for domain, content in contents.items():
        target = CONTRACTS_DIR / domain / "dto.ts"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
        print(f"[ok] 写出 {target.relative_to(PROJECT_ROOT)}")


def check(contents: dict[str, str]) -> int:
    bad = 0
    for domain, content in contents.items():
        target = CONTRACTS_DIR / domain / "dto.ts"
        if not target.exists():
            print(f"[error] 缺失 {target.relative_to(PROJECT_ROOT)}（运行生成模式补齐）")
            bad += 1
            continue
        on_disk = target.read_text(encoding="utf-8")
        if on_disk != content:
            print(f"[error] {target.relative_to(PROJECT_ROOT)} 与生成结果不一致（非幂等）")
            bad += 1
        else:
            print(f"[ok] {target.relative_to(PROJECT_ROOT)} 幂等一致")
    return 1 if bad else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="生成/校验 contracts 域 DTO")
    parser.add_argument("--check", action="store_true", help="幂等校验（CI 门禁），不一致退出 1")
    args = parser.parse_args()

    contents = generate()

    if args.check:
        sys.exit(check(contents))
    write_all(contents)
    print(f"\n[ok] 生成 {len(contents)} 个域，随后运行 --check 验证幂等")


if __name__ == "__main__":
    main()
