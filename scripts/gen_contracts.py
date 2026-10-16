#!/usr/bin/env python3
"""
gen_contracts.py — 从后端真实代码生成契约产物（TS DTO + JSON Schema）

数据来源（三类，均可从仓库本身确定性推导，天然幂等）：
1. SQLAlchemy 模型内省：bothot_entities 的实体列名/类型/可空性 → interface
2. OpenAPI 请求模型：create_app().openapi() 的 components.schemas（Pydantic 请求体）
3. 契约包 Pydantic 模型：app/contracts/<域>.py → JSON Schema（STEP-01 S1.3.1）
   这一类的存在理由就是 ADR-0008：唯一源是 Python 代码，schema 是产物；
   手写 schema 会让"改了模型没人记得改稿"变成常态。

用法：
    python scripts/gen_contracts.py                    # 生成 src/<域>/dto.ts 与 schemas/<域>.schema.json
    python scripts/gen_contracts.py --check            # 幂等校验（CI）：重新生成与磁盘 diff，不一致退出 1
    python scripts/gen_contracts.py --only-schemas     # 只处理 JSON Schema 面（本地调试用）

注意：
- 生成物带「请勿手动修改」头——手工编辑 dto.ts / *.schema.json 会在 --check 下失败
- 分页双口径是冻结契约：bot/hot=page/page_size，knowledge/订阅/任务=limit/offset
- JSON Schema 用 `sort_keys=True` 序列化：键序稳定 ⇒ diff 只反映真实变化；
  **数组不按字典序排**（json.dumps 不动 list），所以 enum 与 required 的顺序仍由模型定义顺序决定
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "apps" / "api"
CONTRACTS_DIR = PROJECT_ROOT / "packages" / "contracts" / "src"
SCHEMAS_DIR = PROJECT_ROOT / "packages" / "contracts" / "schemas"

JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"

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
        # 直接拼块 + 简洁分节注释。旧实现 `_render_domain(...).split("\n", 5)[-1]`
        # 依赖头部行数硬编码，切出残留 `*/` 产生 TS 语法错误（bot/dto.ts:54 实证，
        # 且因 apps/web 仅消费 dist 声明而从未被 tsc 检出）。
        request_block = "// ── 请求模型（Pydantic 请求体，OpenAPI 内省）──\n\n" + "\n\n".join(blocks)
        out[domain] = out[domain].rstrip("\n") + "\n\n" + request_block + "\n"
    return out


# ── JSON Schema 面（STEP-01 S1.3.1：app/contracts/*.py → packages/contracts/schemas/）──

# 契约域名 → 契约模块（模块内每个公开 BaseModel 都会成为一个 $defs 条目）
CONTRACT_SCHEMA_MODULES: dict[str, str] = {
    "collection": "app.contracts.collection",
    "identity": "app.contracts.identity",
    "events": "app.contracts.events",
    "resources": "app.contracts.resources",
}


def _contract_symbols(module_name: str) -> dict[str, Any]:
    """取该模块**自己声明**的公开契约符号：BaseModel 与 Enum 两类。

    两条判据都是刻意的：
    - `obj.__module__ == 模块名` —— 不加就会把 `AwareDatetime` 之类的依赖类型也算成契约形状，
      生成出根本不存在的"契约"；
    - **枚举即使还没被任何模型引用也要出 def** —— `identity.Role` 就是这种情况：
      冻结稿把它当独立 def（带 x-rank 注释），"当前没人引用"是实现状态，不是契约状态。
      第一版只收 BaseModel，于是 Role 从生成物里消失，只能靠登记"它不该消失"来蒙过门禁
      ——那是拿登记遮住生成器的缺口。
    """
    import importlib
    import inspect
    from enum import Enum

    from pydantic import BaseModel

    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    module = importlib.import_module(module_name)
    found: dict[str, Any] = {}
    for name, obj in inspect.getmembers(module, inspect.isclass):
        if name.startswith("_") or obj.__module__ != module.__name__:
            continue
        if obj is BaseModel or (issubclass(obj, BaseModel) and hasattr(obj, "model_fields")):
            found[name] = obj
        elif issubclass(obj, Enum) and obj is not Enum:
            found[name] = obj
    if not found:
        raise SystemExit(f"[error] 契约模块 {module_name} 里没有公开 BaseModel/Enum（配置错误）")
    return dict(sorted(found.items()))


def _strip_titles(node: Any) -> Any:
    """递归剥掉生成物里的 `title` **关键词**（不是名叫 title 的字段）。

    Pydantic 会给每个字段派生一个 title（`response_data` → `"Responsedata"`），那是 UI 文案、
    不是契约事实；第六轮验证点名它被比对器当"strip-title 归一"放过，等于产物长期带着一批
    没人声明、也没人读的键。
    但 `properties` 这张表的键是**字段名**——collection 稿里就真有一个叫 `title` 的字段
    （文章标题，`maxLength: 512`）。第一版把这颗键当关键词一起删了，门禁立刻报
    `ArticleManifest: properties.title 生成=（无此键）`——**我自己写的一刀切，被自己的守卫当场抓住**。
    所以 `properties` 的容器本身不能当 schema 节点处理，只有它的每个值才是。
    """
    if isinstance(node, list):
        return [_strip_titles(x) for x in node]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key == "title":
            continue
        if key == "properties" and isinstance(value, dict):
            out[key] = {name: _strip_titles(schema) for name, schema in value.items()}
        else:
            out[key] = _strip_titles(value)
    return out


def generate_schemas() -> dict[str, str]:
    """返回 {契约域名: schema 文件内容}。"""
    out: dict[str, str] = {}
    for domain, module_name in CONTRACT_SCHEMA_MODULES.items():
        models = _contract_symbols(module_name)
        defs: dict[str, Any] = {}
        for name, model in models.items():
            if not hasattr(model, "model_json_schema"):
                from pydantic import TypeAdapter

                sub = TypeAdapter(model).json_schema(ref_template="#/$defs/{model}")
            else:
                sub = model.model_json_schema(ref_template="#/$defs/{model}")
            # title 一律剥掉：Pydantic 给每个 def 生成 title=类名、给每个字段生成派生 title
            # （`response_data` → `"Responsedata"`），稿里那些 title 是作者写的中文说明。
            # 统一在生成侧剥（而不是留给比对脚本归一）还有个副作用是必要的——
            # 枚举既作为顶层符号出现、又被模型的 $defs 嵌套引用，两处唯一的不同就是 title；
            # 不剥的话冲突守卫会把这种"同一形状的两种写法"误判成两个不同契约。
            sub = _strip_titles(sub)
            for def_name, def_body in sub.pop("$defs", {}).items():
                def_body = _strip_titles(def_body)
                # 同名不同体 ⇒ 立刻响。静默覆盖会让两个域把同一个键写成两种形状而没人知道。
                if def_name in defs and defs[def_name] != def_body:
                    raise SystemExit(
                        f"[error] {domain}: $defs 键冲突 {def_name}（来自 {name}）——"
                        "同名不同体的契约形状必须改名，不能靠覆盖次序决定"
                    )
                defs[def_name] = def_body
            if name in defs and defs[name] != sub:
                raise SystemExit(f"[error] {domain}: 形状 {name} 自相冲突")
            defs[name] = sub
        doc = {
            "$schema": JSON_SCHEMA_DIALECT,
            "$id": f"bothot://contracts/{domain}/v1",
            "title": f"BotHot {domain} 域契约（生成物）",
            "description": (
                f"由 scripts/gen_contracts.py 从 apps/api/app/contracts/{domain}.py 生成，请勿手动修改"
                "（--check 幂等门禁）。唯一源是 Python 模型（ADR-0008）。"
            ),
            "x-generated-by": "scripts/gen_contracts.py",
            "x-source-module": module_name,
            "$defs": defs,
        }
        out[domain] = json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return out


def _schema_target(domain: str) -> Path:
    return SCHEMAS_DIR / f"{domain}.schema.json"


def write_all(contents: dict[str, str]) -> None:
    for domain, content in contents.items():
        target = CONTRACTS_DIR / domain / "dto.ts"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
        print(f"[ok] 写出 {target.relative_to(PROJECT_ROOT)}")


def write_schemas(schemas: dict[str, str]) -> None:
    for domain, content in schemas.items():
        target = _schema_target(domain)
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
        # **逐字节**比较（不是逐字符）：`read_text()` 会把行尾归一，
        # 于是一个 CRLF 版的生成物也能 rc=0——门禁声称"字节一致"却做不到，比放宽更糟。
        # 写侧统一 `newline="\n"`，`.gitattributes` 又钉了 `* text=auto eol=lf`，所以字节比较在
        # 干净检出上等价于字符比较；差别只会在"有人本地用 CRLF 编辑器改过产物"时现形——那正是该抓的。
        payload = content.encode("utf-8")
        if target.read_bytes() != payload:
            print(f"[error] {target.relative_to(PROJECT_ROOT)} 与生成结果不一致（非幂等，字节比较）")
            bad += 1
        else:
            print(f"[ok] {target.relative_to(PROJECT_ROOT)} 幂等一致")
    return 1 if bad else 0


def check_schemas(schemas: dict[str, str]) -> int:
    """与 check() 同纪律：逐字节比较，不做"语义相同就行"的宽容。

    这里故意严格——漂移门禁的价值在于"任何一处不一致都要有人来看"。
    真要放宽，应该在 S1.3.2 的**语义比对**那一步放宽，而不是在这一步放宽。
    """
    bad = 0
    for domain, content in schemas.items():
        target = _schema_target(domain)
        if not target.exists():
            print(f"[error] 缺失 {target.relative_to(PROJECT_ROOT)}（运行生成模式补齐）")
            bad += 1
            continue
        if target.read_bytes() != content.encode("utf-8"):
            print(f"[error] {target.relative_to(PROJECT_ROOT)} 与生成结果不一致（非幂等，字节比较）")
            bad += 1
        else:
            print(f"[ok] {target.relative_to(PROJECT_ROOT)} 幂等一致")
    return 1 if bad else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="生成/校验 contracts 域 DTO 与 JSON Schema")
    parser.add_argument("--check", action="store_true", help="幂等校验（CI 门禁），不一致退出 1")
    parser.add_argument("--only-schemas", action="store_true", help="只处理 JSON Schema 面")
    args = parser.parse_args()

    schemas = generate_schemas()
    contents: dict[str, str] = {} if args.only_schemas else generate()

    if args.check:
        # 两面都要跑完再判定：写成 `check(contents) or check_schemas(schemas)` 会在第一面
        # 已经失败时**短路**，第二面的差异就再也打不出来——门禁只报一半问题等于误导。
        rc = (0 if args.only_schemas else check(contents)) | check_schemas(schemas)
        sys.exit(1 if rc else 0)
    if contents:
        write_all(contents)
    write_schemas(schemas)
    print(f"\n[ok] 生成 {len(contents)} 个 dto 域 + {len(schemas)} 个 schema 域，随后运行 --check 验证幂等")


if __name__ == "__main__":
    main()
