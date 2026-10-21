"""STEP-08 S8.1.1：`source_identifiers` 的形状一致性与两条 DB 侧不变量。

为什么要三条一起写：这张表的意义全在"形状对得上 + 约束真的在 DB 侧"。
少任何一条，都能出现"模型里有、库里没有"或"CI 建的表和单测读的表不是一份"。

对齐是**三方**的：实体、迁移的 `create_table`、CI 往返探针的 `SHAPES` 登记。
探针那份不是文档抄件——它是 `--expect=present/absent` 实际比对的集合，
三方里任意两方不一致，本文件就红（`SHAPES` 缺登记时探针自己也会红，那是另一道门）。
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import Source, SourceIdentifier

REPO = Path(__file__).resolve().parents[3]
MIGRATION = REPO / "apps/api/alembic/versions/ab1006c2a_source_identifiers.py"
PROBE = REPO / "scripts/migration_roundtrip_probe.py"
REVISION = "ab1006c2a"


def _migration_columns() -> list[str]:
    """从磁盘上的迁移里取 `create_table` 的列名（不是抄本，是它自己声明的那一份）。"""
    tree = ast.parse(MIGRATION.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "create_table":
            names: list[str] = []
            for arg in node.args[1:]:
                if isinstance(arg, ast.Call) and getattr(arg.func, "attr", "") == "Column" and arg.args:
                    first = arg.args[0]
                    if isinstance(first, ast.Constant) and isinstance(first.value, str):
                        names.append(first.value)
            return names
    raise AssertionError("迁移里找不到 create_table")


def _probe_shape() -> dict[str, Any]:
    import importlib.util

    spec = importlib.util.spec_from_file_location("migration_roundtrip_probe", PROBE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    shape = module.SHAPES.get(REVISION)
    assert shape is not None, f"新头 {REVISION} 没在 SHAPES 登记 ⇒ CI 往返步会当场判红"
    return shape


# ------------------------------------------------------------------ 形状三方对账


def test_model_migration_and_probe_agree_on_columns() -> None:
    from_model = [c.name for c in SourceIdentifier.__table__.columns]
    from_migration = _migration_columns()
    from_probe = sorted(_probe_shape()["columns"]["source_identifiers"])
    assert sorted(from_model) == sorted(from_migration), (from_model, from_migration)
    assert sorted(from_model) == from_probe, (from_model, from_probe)


def test_migration_is_a_single_head_with_the_expected_parent() -> None:
    tree = ast.parse(MIGRATION.read_text(encoding="utf-8"))
    consts = {
        node.target.id: node.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and isinstance(node.value, ast.Constant)
    }
    assert consts["revision"] == REVISION
    # 父是 STEP-28 的 `ab1006c4a`，不是卡面当年写的 `ab1006c1a`：
    # 那张卡的字段 9 明文"down_revision 以合入时 alembic heads 为准，单头"。
    assert consts["down_revision"] == "ab1006c4a", consts["down_revision"]


def test_unique_constraint_name_is_declared_in_both_places() -> None:
    """`(kind, value)` 唯一是本表的不变量 1，名字必须在迁移与探针里同形。

    只有一边有名字 = 降级后探针查不到它消失，或反过来在断言一个不存在的东西。
    """
    name = "uq_source_identifier_kind_value"
    assert name in MIGRATION.read_text(encoding="utf-8")
    assert name in _probe_shape()["indexes"]


# ------------------------------------------------------------------ DB 侧不变量（连库）


async def test_same_kind_and_value_belongs_to_one_source_only(db_session: AsyncSession) -> None:
    tag = id(db_session)
    a = Source(type="wechat_oa", external_id=f"s08-a-{tag}", name="a")
    b = Source(type="wechat_oa", external_id=f"s08-b-{tag}", name="b")
    db_session.add_all([a, b])
    await db_session.flush()

    db_session.add(SourceIdentifier(source_id=a.id, kind="biz", value=f"BIZ-DUP-{tag}", origin="source"))
    await db_session.flush()
    db_session.add(SourceIdentifier(source_id=b.id, kind="biz", value=f"BIZ-DUP-{tag}", origin="source"))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_the_same_value_under_a_different_kind_is_a_different_fact(db_session: AsyncSession) -> None:
    """biz 与 ghid 允许同值：唯一性是"同一种标识内"的，跨种相等不代表同一号主。"""
    tag = id(db_session)
    src = Source(type="wechat_oa", external_id=f"s08-c-{tag}", name="c")
    db_session.add(src)
    await db_session.flush()
    value = f"SHARED-{tag}"
    db_session.add_all(
        [
            SourceIdentifier(source_id=src.id, kind="biz", value=value, origin="source"),
            SourceIdentifier(source_id=src.id, kind="ghid", value=value, origin="resolver"),
        ]
    )
    await db_session.flush()
    rows = (
        await db_session.execute(
            select(SourceIdentifier.kind).where(SourceIdentifier.source_id == src.id).order_by(SourceIdentifier.kind)
        )
    ).scalars().all()
    assert sorted(rows) == ["biz", "ghid"]


async def test_deleting_the_source_takes_its_identifiers(db_session: AsyncSession) -> None:
    """级联删除：源没了不留孤儿标识（否则反查会命中一个不存在的源）。"""
    tag = id(db_session)
    src = Source(type="wechat_oa", external_id=f"s08-d-{tag}", name="d")
    db_session.add(src)
    await db_session.flush()
    db_session.add(SourceIdentifier(source_id=src.id, kind="ghid", value=f"gh_{tag}", origin="resolver"))
    await db_session.flush()
    owner = src.id

    await db_session.delete(src)
    await db_session.flush()
    left = (
        await db_session.execute(select(SourceIdentifier).where(SourceIdentifier.source_id == owner))
    ).scalars().all()
    assert left == [], "CASCADE 没生效：孤儿标识会让按标识反查源的路径命中空对象"
