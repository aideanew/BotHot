#!/usr/bin/env python3
"""STEP-73：`/chat` 可检索种子（空间 → 资产 → 文档 三张表 + 一个源）。

**直写表是测试夹具，不是产品路径**（D-V24-12）。产品侧的建空间/建文档走
`app/services/...` + LangBot 建库返回的 `kb_uuid`/`file_id`；本脚本绕过那一整条链，
把 D-V24-12 需要的三个值直接摆进库，好让 `chat.py` 的 `allowed_file_ids` 非空、
`_filter_by_allowed` 能留下假 LangBot 返回的那一条。它的存在**不**说明产品有"直写表"的能力，
也不覆盖建库/上传/ingest/删除任何一条真实路径。

为什么要有它：`chat.py:83-96` 的候选集合来自本空间的 `langbot_file_id`；集合为空时
检索结果会被整体过滤掉，`ask` 表现为"检索到了但上下文为空"——那不是缺陷，是没种子。

口径三条：
1. **不建用户**：用户由 `apps/api/scripts/qa_seed_sessions.py` 建（卡面 S73.1）。
   本脚本只读 `users` 行；读不到就退出码 3 并指路，不自己插一条。
2. **幂等**：四张表都按各自的唯一键 get-or-create（`knowledge_spaces(user_id,name)`、
   `sources(type,external_id)`、`content_assets(source_id,external_id)`、
   `knowledge_documents(asset_id,space_id)`），已存在则把值修正回夹具口径。
3. **两遍自证**：进程内连做两遍 apply，并打印两遍后的行数。第二遍走的是"已存在 ⇒ 只更新"
   那条分支，与跨进程第二次跑同一条代码路径（区别只是同一个进程，见证据里的局限说明）。

stdout 形状（启动器按 `^space_id=` 取，并追加成 seed 文件的 `space <id>` 行）：
    space_id=<uuid>
    pass1 counts: spaces=… sources=… assets=… documents=…
    pass2 counts: …
    <四行读数：space / source / asset / document 的实际列值>

退出码：0 正常；3 `users` 表里没有该 sub；4 两遍结果不一致（幂等破了）。
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import sys
from pathlib import Path

_API_ROOT = Path(__file__).resolve().parents[2] / "apps" / "api"
sys.path.insert(0, str(_API_ROOT))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker  # noqa: E402

from app.db import create_engine_and_session  # noqa: E402
from app.models.entities import (  # noqa: E402
    ContentAsset,
    KnowledgeDocument,
    KnowledgeSpace,
    Source,
    User,
)

if sys.platform == "win32":
    # psycopg async 不兼容 Windows 默认 ProactorEventLoop，须换 Selector 实现
    # （与 apps/api/scripts/qa_seed_sessions.py 同一处成因，同一处理）。
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

SPACE_NAME = "R24 流式验收空间"
KB_UUID = "fake-kb-1"
# 与 scripts/e2e/fake_langbot.py 的 FILE_NAME 逐字相同（卡面验收第 5 条）——两边任一侧改名，
# `_filter_by_allowed` 就会把整条结果过滤掉，而那种失败读起来像"检索为空"。
FILE_ID = "fake-doc-1"
SOURCE_TYPE = "web"
SOURCE_EXTERNAL_ID = "r24-fake-source"
ASSET_EXTERNAL_ID = "r24-fake-doc-1"
ASSET_TITLE = "R24 假文章"
ASSET_URL = "http://127.0.0.1:3291/fake-article"
MARKDOWN = "R24 假文章正文（STEP-73 夹具，内容本身不参与判据）。"
# 由正文派生而不手抄：同一份正文 ⇒ 同一串，跨机器可复算；也顺手满足「64 位」这个形状要求。
CONTENT_HASH = hashlib.sha256(MARKDOWN.encode("utf-8")).hexdigest()
# qa_seed_sessions.py 的 ACCOUNTS[0]（role=admin）。只在 E2E_SEED_FILE 缺席时用到。
DEFAULT_SUB = "qa-admin-001"


def _seed_sub() -> str:
    """优先用 E2E_SEED_FILE 里第一条 `session <sub>:` 的 sub，否则回落 admin。"""
    path = os.environ.get("E2E_SEED_FILE")
    if path:
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        m = re.search(r"^session (\S+):", text, re.MULTILINE)
        if m:
            return m.group(1)
    return DEFAULT_SUB


async def _apply(factory: async_sessionmaker[AsyncSession], user_id: str) -> str:
    """幂等 upsert 一遍（空间 → 源 → 资产 → 文档），返回 space id。"""
    async with factory() as session:
        space = (
            await session.execute(
                select(KnowledgeSpace).where(
                    KnowledgeSpace.user_id == user_id, KnowledgeSpace.name == SPACE_NAME
                )
            )
        ).scalar_one_or_none()
        if space is None:
            space = KnowledgeSpace(user_id=user_id, name=SPACE_NAME)
            session.add(space)
        space.langbot_kb_uuid = KB_UUID
        space.status = "ACTIVE"
        space.engine = "builtin"
        space.engine_kb_id = KB_UUID
        await session.flush()
        space_id = space.id

        source = (
            await session.execute(
                select(Source).where(Source.type == SOURCE_TYPE, Source.external_id == SOURCE_EXTERNAL_ID)
            )
        ).scalar_one_or_none()
        if source is None:
            source = Source(type=SOURCE_TYPE, external_id=SOURCE_EXTERNAL_ID, url=ASSET_URL)
            session.add(source)
        source.name = "R24 假源"
        source.url = ASSET_URL
        source.status = "ACTIVE"
        await session.flush()

        asset = (
            await session.execute(
                select(ContentAsset).where(
                    ContentAsset.source_id == source.id, ContentAsset.external_id == ASSET_EXTERNAL_ID
                )
            )
        ).scalar_one_or_none()
        if asset is None:
            asset = ContentAsset(source_id=source.id, external_id=ASSET_EXTERNAL_ID, content_hash=CONTENT_HASH)
            session.add(asset)
        asset.url = ASSET_URL
        asset.title = ASSET_TITLE
        asset.content_type = "article"
        asset.content_hash = CONTENT_HASH
        asset.content_markdown = MARKDOWN
        asset.status = "READY"
        await session.flush()
        asset_id = asset.id

        doc = (
            await session.execute(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.asset_id == asset_id, KnowledgeDocument.space_id == space_id
                )
            )
        ).scalar_one_or_none()
        if doc is None:
            doc = KnowledgeDocument(asset_id=asset_id, space_id=space_id)
            session.add(doc)
        doc.langbot_file_id = FILE_ID
        doc.status = "READY"
        doc.content_hash = CONTENT_HASH
        await session.commit()
    return space_id


async def _counts(
    factory: async_sessionmaker[AsyncSession], user_id: str, space_id: str
) -> tuple[int, int, int, int]:
    """按四张表各自的夹具键计数（行数没变 = 第二遍没新增）。"""
    async with factory() as session:
        spaces = (
            await session.execute(
                select(func.count())
                .select_from(KnowledgeSpace)
                .where(KnowledgeSpace.user_id == user_id, KnowledgeSpace.name == SPACE_NAME)
            )
        ).scalar_one()
        sources = (
            await session.execute(
                select(func.count())
                .select_from(Source)
                .where(Source.type == SOURCE_TYPE, Source.external_id == SOURCE_EXTERNAL_ID)
            )
        ).scalar_one()
        assets = (
            await session.execute(
                select(func.count()).select_from(ContentAsset).where(ContentAsset.external_id == ASSET_EXTERNAL_ID)
            )
        ).scalar_one()
        docs = (
            await session.execute(
                select(func.count()).select_from(KnowledgeDocument).where(KnowledgeDocument.space_id == space_id)
            )
        ).scalar_one()
    return int(spaces), int(sources), int(assets), int(docs)


async def _readings(factory: async_sessionmaker[AsyncSession], space_id: str) -> list[str]:
    """把验收要读的四列原样打出来（`select … where …` 的等价读数，省掉一次 psql）。"""
    async with factory() as session:
        space = (
            await session.execute(select(KnowledgeSpace).where(KnowledgeSpace.id == space_id))
        ).scalar_one()
        source = (
            await session.execute(
                select(Source).where(Source.type == SOURCE_TYPE, Source.external_id == SOURCE_EXTERNAL_ID)
            )
        ).scalar_one()
        asset = (
            await session.execute(
                select(ContentAsset).where(
                    ContentAsset.source_id == source.id, ContentAsset.external_id == ASSET_EXTERNAL_ID
                )
            )
        ).scalar_one()
        doc = (
            await session.execute(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.asset_id == asset.id, KnowledgeDocument.space_id == space.id
                )
            )
        ).scalar_one()
    return [
        f"space: id={space.id} name={space.name!r} langbot_kb_uuid={space.langbot_kb_uuid!r}"
        f" engine={space.engine!r} engine_kb_id={space.engine_kb_id!r} status={space.status!r}",
        f"source: id={source.id} type={source.type!r} external_id={source.external_id!r}",
        f"asset: id={asset.id} external_id={asset.external_id!r} title={asset.title!r}"
        f" content_hash={asset.content_hash} status={asset.status!r}",
        f"document: id={doc.id} space_id={doc.space_id} langbot_file_id={doc.langbot_file_id!r}"
        f" status={doc.status!r} content_hash={doc.content_hash}",
    ]


async def main() -> int:
    sub = _seed_sub()
    engine, factory = create_engine_and_session()
    try:
        async with factory() as session:
            user = (await session.execute(select(User).where(User.sub == sub))).scalar_one_or_none()
        if user is None:
            print(
                f"❌ users 表里没有 sub={sub}；先跑 apps/api/scripts/qa_seed_sessions.py"
                f"（本脚本不建用户，卡面 S73.1）",
                file=sys.stderr,
            )
            return 3

        first = await _apply(factory, user.id)
        c1 = await _counts(factory, user.id, first)
        second = await _apply(factory, user.id)
        c2 = await _counts(factory, user.id, second)

        print(f"space_id={first}")
        print(f"pass1 counts: spaces={c1[0]} sources={c1[1]} assets={c1[2]} documents={c1[3]}")
        print(f"pass2 counts: spaces={c2[0]} sources={c2[1]} assets={c2[2]} documents={c2[3]}")
        if first != second or c1 != c2:
            print(
                f"❌ 幂等破了：space_id {first} → {second}，counts {c1} → {c2}",
                file=sys.stderr,
            )
            return 4
        for line in await _readings(factory, first):
            print(line)
    finally:
        await engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
