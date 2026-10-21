#!/usr/bin/env python3
"""迁移往返的**结构探针**（STEP-04 S4.2 补完轮，2026-10-17）。

为什么要有这个文件：CI 的 "Migration roundtrip" 步原本只比 `alembic current` 的字符串。
`alembic downgrade -1` 即使在 `downgrade()` 里**什么都不做**（先例
`ab1004w1a_secret_aes.py:119-121` 的 downgrade 只打一行 warning 就返回）也会把
`alembic_version` 重标成父版本，于是"版本变了"根本不等价于"形状真的被拆掉了"。
本探针直查 `information_schema` / `pg_indexes`，把"DDL 可逆"从说法变成读数。

判据本体是纯函数 `evaluate()`，不需要 PG 就能被单测钉住极性
（见 `apps/api/tests/test_manifest_asset_alignment.py::test_roundtrip_probe_has_polarity`）；
连库部分只在 `main()` 里，`psycopg` 延迟 import，所以离线场景 import 本模块也不会失败。

归属说明：本文件与 `.github/workflows/ci.yml` 同属"验收门禁"面（00C/00E 家族），
不在 STEP-04 来源卡的所有权清单内；新增它是为了消灭一条没有执行者的口径。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# 本步引入的形状：降级后必须全部消失，再升级后必须全部回来。
#
# **按 revision 登记，而不是钉死某一支迁移**（2026-10-21 改造）。原实现是两张全局字典，
# 里面只有 STEP-04 那一次改动的列与索引；后果不是"少检了新表"这么温和——它是
# **任何新头一出现这一步就恒红**：`alembic downgrade -1` 落到旧的 head，那里的
# `article_key`/`manifest_id` 本来就该还在，而被检的却是"STEP-04 的形状必须消失"。
# 现在检的是**当前 head 自己声明的形状**，且**新头不在此登记就直接判红**（宁可拦得住也不静默）。
#
# 索引仍带**表坐标**。同一批改动刚把 AST 门从"两表索引名并集"改成按表判，
# 探针若只按名字判就等于留下两个精度不同的判据；PG 里索引名在 schema 内唯一，
# 所以这里能抓到的不是"第二支同名索引"，而是"建到别的表上"那一类错。
SHAPES: dict[str, dict[str, object]] = {
    "ab1006c1a": {
        "columns": {"article_manifests": ["article_key"], "job_items": ["manifest_id"]},
        "indexes": {"ix_manifest_source_article_key": "article_manifests", "ix_job_items_manifest_id": "job_items"},
    },
    "ab1006c4a": {
        # STEP-28 S28.1.1：只建一张表、四个列、零索引（索引留给真正按它查询的卡）
        "columns": {"system_settings": ["key", "value", "updated_by", "updated_at"]},
        "indexes": {},
    },
    "ab1006c2a": {
        # STEP-08 S8.1.1：一源多标识。列与索引都按迁移声明逐条对账——
        # `(kind, value)` 的唯一性是这张表的存在理由之一（同一标识不得属于两个源），
        # 所以它的索引名必须在"降级后消失"的清单里，不能只探列。
        "columns": {
            "source_identifiers": ["id", "source_id", "kind", "value", "origin", "created_at"]
        },
        "indexes": {
            "uq_source_identifier_kind_value": "source_identifiers",
            "ix_source_identifiers_source_id": "source_identifiers",
            "ix_source_identifiers_kind": "source_identifiers",
        },
    },
}


# STEP-04 那一份形状的两个别名：`evaluate()` 的 `shape=None` 走它们，
# 目的是让已有的八条极性断言不必跟着改（它们验的是判据本身，不是"哪一支是 head"）。
_LEGACY_COLUMNS: dict[str, str] = {"article_manifests": "article_key", "job_items": "manifest_id"}
_LEGACY_INDEXES: dict[str, str] = {
    "ix_manifest_source_article_key": "article_manifests",
    "ix_job_items_manifest_id": "job_items",
}

# 兼容公开名：既有的极性用例按这两个名字构造"应有集合"。它们是上面那一份的只读别名，
# 不是第二个真源——判据取形状一律走 `SHAPES[head]`（见 `resolve_shape`）。
COLUMNS = _LEGACY_COLUMNS
INDEXES = _LEGACY_INDEXES


def evaluate(
    have_columns: set[tuple[str, str]],
    have_indexes: set[tuple[str, str]],
    expect: str,
    shape: dict[str, object] | None = None,
) -> list[str]:
    """返回违规清单（空 = 通过）。`expect` 取 "present" 或 "absent"；两个集合的元素都是 `(表名, 名字)`。

    `shape=None` 只保留给旧的调用方式；CI 步走的是"当前 head 自己声明的那一份"（见 `main`）。
    """
    if expect not in ("present", "absent"):
        return [f"未知的 expect={expect!r}（只支持 present/absent）"]
    if shape is None:
        shape = {
            "columns": {t: [c] for t, c in _LEGACY_COLUMNS.items()},
            "indexes": dict(_LEGACY_INDEXES),
        }
    cols_map = shape["columns"]
    assert isinstance(cols_map, dict)
    idx_map = shape["indexes"]
    assert isinstance(idx_map, dict)
    want_cols = {(t, c) for t, cs in cols_map.items() for c in cs}
    want_idx = {(table, name) for name, table in idx_map.items()}
    if expect == "present":
        missing_cols = sorted(want_cols - have_columns)
        missing_idx = sorted(want_idx - have_indexes)
        return [
            *(f"缺列 {t}.{c}" for t, c in missing_cols),
            *(f"缺索引 {t}.{i}" for t, i in missing_idx),
        ]
    leaked_cols = sorted(want_cols & have_columns)
    # absent 侧按**名字**判（不按表）：索引名在 PG 的 schema 内全局唯一，
    # 所以降级后只要还留着这个名字就是"没拆干净"，哪怕它报在别的表上也要出声。
    leaked_idx = sorted({p for p in have_indexes if p[1] in idx_map})
    return [
        *(f"降级后仍在：列 {t}.{c}" for t, c in leaked_cols),
        *(f"降级后仍在：索引 {t}.{i}" for t, i in leaked_idx),
    ]


def query_shape(dsn: str, shape: dict[str, object]) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    """连库读实际形状。DSN 允许带 SQLAlchemy 的 `+psycopg` 方言前缀。

    两条查询都只用 `= ANY(%s)`（列表参数在 psycopg3 里自适应成 ARRAY），
    不写 `(table_name, column_name) IN %s` 那种行构造器——它在不同驱动版本下的
    参数展开不一样，而探针本身必须是零歧义的那一方。
    列按 `(表, 列)` 在 Python 侧收敛（同名列可能属于别的表），
    索引则**保留 SQL 返回的全部 `(表, 名)` 对**——名字在 schema 内全局唯一，
    降级后不管它报在哪张表上都算"没拆干净"。
    """
    import psycopg  # 延迟 import：离线判据（单测）不该依赖驱动

    cols_map = shape["columns"]
    assert isinstance(cols_map, dict)
    idx_map = shape["indexes"]
    assert isinstance(idx_map, dict)
    want_cols = {c for cs in cols_map.values() for c in cs}
    # connect_timeout 是实测逼出来的：本机第一次拿一个不通的地址试，psycopg 默认**不带超时**，
    # 整个探针挂在 SYN 上不动（Windows 上表现为长时间无输出）。CI 里同等情形会让 job 挂到
    # workflow timeout，比红更难定位。给它 10 秒，失败就走 `_shape_or_die` 的出声路径。
    conn = psycopg.connect(dsn.replace("+psycopg", ""), connect_timeout=10)
    try:
        cols = {
            (t, c)
            for t, c in conn.execute(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE column_name = ANY(%s)",
                (sorted(want_cols),),
            ).fetchall()
            if t in cols_map and c in cols_map[t]
        }
        idx = {
            (t, n)
            for t, n in conn.execute(
                "SELECT tablename, indexname FROM pg_indexes WHERE indexname = ANY(%s)", (sorted(idx_map),)
            ).fetchall()
        }
    finally:
        conn.close()
    return cols, idx


def head_revision(versions_dir: Path | None = None) -> list[str]:
    """扫 `alembic/versions/` 推出 head（不被任何版本当作 `down_revision` 的那些 revision）。

    返回**列表**而不是单个：分叉（>1 个 head）必须由调用方出声，不能在这里悄悄挑第一个。
    解析用最朴素的两行正则——这些文件是 alembic 生成的模板，字段名固定；
    真要 import alembic 就得在 CI 的探查步骤里装依赖，探针的立足点是"零依赖也能判"。
    """
    root = versions_dir or Path(__file__).resolve().parents[1] / "apps" / "api" / "alembic" / "versions"
    revs: dict[str, str | None] = {}
    for path in sorted(root.glob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        m = re.search(r'^revision(?::\s*str)?\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
        if not m:
            continue
        d = re.search(r'^down_revision(?::[^=]*)?\s*=\s*(["\'])([^"\']*)\1', text, re.MULTILINE)
        revs[m.group(1)] = d.group(2) if d and d.group(2) else None
    children = {v for v in revs.values() if v}
    return sorted(r for r in revs if r not in children)


def resolve_shape(revision: str) -> tuple[dict[str, object] | None, list[str]]:
    """返回 `(形状, 问题清单)`。新头不在此声明形状 = 探针判红，不静默放行。

    这一条是本次改造的承重部分：旧写法下"新头没人登记"表现为**恒红**（谁都动不了），
    而完全按动态推又不检查任何东西（恒绿）。现在它是**恒响**：漏登记会被点名，且点名内容直接给出要填哪一份。
    """
    if revision not in SHAPES:
        return None, [
            f"当前 head={revision!r} 没有在本文件的 SHAPES 里声明待验形状"
            "（columns: 表→列集合，indexes: 索引名→表）⇒ 新迁移必须登记，否则往返门不知道该检什么"
        ]
    return SHAPES[revision], []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--expect", required=True, choices=("present", "absent"))
    ap.add_argument("--dsn", default=os.environ.get("DATABASE_URL", ""))
    ap.add_argument("--revision", default="", help="留空 = 从 alembic/versions/ 动态推 head")
    args = ap.parse_args(argv)
    if not args.dsn:
        print("探针失败：没有 DSN（--dsn 或环境变量 DATABASE_URL）", file=sys.stderr)
        return 2
    revision = args.revision
    if not revision:
        heads = head_revision()
        if len(heads) != 1:
            print(f"探针失败：alembic/versions/ 推出 {len(heads)} 个 head {heads}（分叉或读不出）", file=sys.stderr)
            return 1
        revision = heads[0]
    shape, problems = resolve_shape(revision)
    for line in problems:
        print(f"  ❌ {line}", file=sys.stderr)
    if problems:
        return 1
    assert shape is not None
    cols, idx = _shape_or_die(args.dsn, shape)
    print(f"roundtrip probe revision={revision} expect={args.expect} 实得列={sorted(cols)} 索引={sorted(idx)}")
    bad = evaluate(cols, idx, args.expect, shape)
    for line in bad:
        print(f"  ❌ {line}", file=sys.stderr)
    return 1 if bad else 0


def _shape_or_die(dsn: str, shape: dict[str, object]) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    """连库失败 ⇒ 打印原因并以非零退出（探针绝不 fail-open：连不上就等于没证明）。"""
    try:
        return query_shape(dsn, shape)
    except Exception as exc:  # noqa: BLE001 —— 任何驱动/网络错都要变红，而不是绿着跳过
        print(f"探针无法读取库形状（dsn 方言/网络/权限）：{type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    sys.exit(main())
