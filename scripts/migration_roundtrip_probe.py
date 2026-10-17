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
import sys

# 本步引入的形状：降级后必须全部消失，再升级后必须全部回来
COLUMNS: dict[str, str] = {"article_manifests": "article_key", "job_items": "manifest_id"}
# 索引也带**表坐标**。同一批改动刚把 AST 门从"两表索引名并集"改成按表判，
# 探针若只按名字判就等于留下两个精度不同的判据；PG 里索引名在 schema 内唯一，
# 所以这里能抓到的不是"第二支同名索引"，而是"建到别的表上"那一类错。
INDEXES: dict[str, str] = {
    "ix_manifest_source_article_key": "article_manifests",
    "ix_job_items_manifest_id": "job_items",
}


def evaluate(
    have_columns: set[tuple[str, str]],
    have_indexes: set[tuple[str, str]],
    expect: str,
) -> list[str]:
    """返回违规清单（空 = 通过）。`expect` 取 "present" 或 "absent"；两个集合的元素都是 `(表名, 名字)`。"""
    if expect not in ("present", "absent"):
        return [f"未知的 expect={expect!r}（只支持 present/absent）"]
    want_cols = set(COLUMNS.items())
    want_idx = {(table, name) for name, table in INDEXES.items()}
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
    leaked_idx = sorted({p for p in have_indexes if p[1] in INDEXES})
    return [
        *(f"降级后仍在：列 {t}.{c}" for t, c in leaked_cols),
        *(f"降级后仍在：索引 {t}.{i}" for t, i in leaked_idx),
    ]


def query_shape(dsn: str) -> tuple[set[tuple[str, str]], set[str]]:
    """连库读实际形状。DSN 允许带 SQLAlchemy 的 `+psycopg` 方言前缀。

    两条查询都只用 `= ANY(%s)`（列表参数在 psycopg3 里自适应成 ARRAY），
    不写 `(table_name, column_name) IN %s` 那种行构造器——它在不同驱动版本下的
    参数展开不一样，而探针本身必须是零歧义的那一方。
    列按 `(表, 列)` 在 Python 侧收敛（同名列可能属于别的表），
    索引则**保留 SQL 返回的全部 `(表, 名)` 对**——名字在 schema 内全局唯一，
    降级后不管它报在哪张表上都算"没拆干净"。
    """
    import psycopg  # 延迟 import：离线判据（单测）不该依赖驱动

    want_cols = {c for c in COLUMNS.values()}
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
            if t in COLUMNS and COLUMNS[t] == c
        }
        idx = {
            (t, n)
            for t, n in conn.execute(
                "SELECT tablename, indexname FROM pg_indexes WHERE indexname = ANY(%s)", (sorted(INDEXES),)
            ).fetchall()
        }
    finally:
        conn.close()
    return cols, idx


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--expect", required=True, choices=("present", "absent"))
    ap.add_argument("--dsn", default=os.environ.get("DATABASE_URL", ""))
    args = ap.parse_args(argv)
    if not args.dsn:
        print("探针失败：没有 DSN（--dsn 或环境变量 DATABASE_URL）", file=sys.stderr)
        return 2
    cols, idx = _shape_or_die(args.dsn)
    print(f"roundtrip probe expect={args.expect} 实得列={sorted(cols)} 索引={sorted(idx)}")
    bad = evaluate(cols, idx, args.expect)
    for line in bad:
        print(f"  ❌ {line}", file=sys.stderr)
    return 1 if bad else 0


def _shape_or_die(dsn: str) -> tuple[set[tuple[str, str]], set[str]]:
    """连库失败 ⇒ 打印原因并以非零退出（探针绝不 fail-open：连不上就等于没证明）。"""
    try:
        return query_shape(dsn)
    except Exception as exc:  # noqa: BLE001 —— 任何驱动/网络错都要变红，而不是绿着跳过
        print(f"探针无法读取库形状（dsn 方言/网络/权限）：{type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    sys.exit(main())
