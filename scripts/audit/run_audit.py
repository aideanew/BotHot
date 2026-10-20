#!/usr/bin/env python3
"""存量审计执行器（STEP-07 S07.V15.1）：只跑 SELECT，且**每次取数都在只读事务里**。

三条设计取舍：

1. **只读不是口头承诺**。每条查询前一句 `SET TRANSACTION READ ONLY`，并回读
   `SHOW transaction_read_only` 把实际值打在输出里；再加 `--self-test-write-refused`
   一发，主动在只读事务里试一句 `CREATE TABLE`，**必须失败**才算这条判据成立。
   没有这一发，"脚本只发 SELECT"只是我对 SQL 文本的静态判断，不是数据库的执行事实。
2. **静态门与运行时门并存**。`queries.is_read_only()` 在取数前就拒掉任何非单条 SELECT
   的语句（多语句夹带、写关键字），这样即便有人日后往表里加了一条 UPDATE，
   脚本也会在连库之前就停住。
3. **读数只有计数**。审计输出不含任何行内容、URL、正文或凭据（卡面 §1「结果入 EVD，
   不含个人数据」）。

连接串一律参数传入，脚本里没有默认 DSN——写死一个"本机的库"就等于给生产留了一条捷径。

用法：
    python scripts/audit/run_audit.py --dsn postgresql://ro_user@prod-host:5432/bothot
    python scripts/audit/run_audit.py --dsn ... --only A6 --json
    python scripts/audit/run_audit.py --dsn ... --self-test-write-refused
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from queries import QUERIES, AuditQuery, by_id, is_read_only  # noqa: E402

PROBE_SQL = "CREATE TABLE IF NOT EXISTS bothot_audit_write_probe (id integer)"


def _connect(dsn: str) -> Any:
    import psycopg

    return psycopg.connect(dsn, autocommit=False, connect_timeout=5)


def run_query(conn: Any, query: AuditQuery) -> tuple[int, str]:
    """在只读事务里取一条审计读数，返回 `(计数, transaction_read_only 实际值)`。

    只读声明必须是事务的第一句，所以它排在查询前面；`SHOW` 在同一事务里回读实际生效值
    ——如果角色或数据库配置让 `read_only` 落不回 `on`，调用方会把这条读数判为不可信。
    """
    if not is_read_only(query.sql):
        raise ValueError(f"{query.id} 不是单条只读 SELECT，拒绝执行：{query.sql[:60]!r}")
    with conn.transaction():
        conn.execute("SET TRANSACTION READ ONLY")
        observed = str(conn.execute("SHOW transaction_read_only").fetchone()[0])
        count = int(conn.execute(query.sql).fetchone()[0])
    return count, observed


def write_probe(conn: Any) -> str:
    """在只读事务里试写一次：**必须失败**。返回被拒时数据库给的原文。

    没有失败就抛 `RuntimeError`——一条号称只读的连接如果可以写，本脚本给出的所有读数
    都失去前提（写坏生产数据的责任在跑脚本的人，不在数据库）。
    """
    try:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            conn.execute(PROBE_SQL)
    except Exception as exc:  # noqa: BLE001  # 这里要的就是"被拒"这个事实
        conn.rollback()
        return str(exc).strip().splitlines()[0]
    raise RuntimeError("只读事务竟然允许写入：本脚本拒绝在任何读数上签字")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="存量审计（只读）")
    parser.add_argument("--dsn", required=True, help="libpq 连接串（必填，脚本内无默认值）")
    parser.add_argument("--only", default="", help="只跑这些 id（逗号分隔，如 A3,A6）")
    parser.add_argument("--json", action="store_true", help="按 JSON 行输出，便于落证据")
    parser.add_argument(
        "--self-test-write-refused",
        action="store_true",
        help="额外验一发：在只读事务里试写，必须被数据库拒绝",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ids = [item.strip() for item in args.only.split(",") if item.strip()]
    queries = [by_id(item) for item in ids] if ids else list(QUERIES)

    conn = _connect(args.dsn)
    try:
        rows: list[dict[str, Any]] = []
        if args.self_test_write_refused:
            refused = write_probe(conn)
            rows.append({"id": "SELF-TEST", "name": "只读事务拒写", "value": refused})
        for query in queries:
            count, observed = run_query(conn, query)
            if observed != "on":
                print(f"❌ {query.id} 事务只读未生效（read_only={observed}），读数不作数", file=sys.stderr)
                return 2
            rows.append({"id": query.id, "name": query.name, "count": count, "read_only": observed})
    finally:
        conn.close()

    for row in rows:
        if args.json:
            print(json.dumps(row, ensure_ascii=False))
        else:
            print(f"{row['id']:<9} {row.get('count', row.get('value'))}\t{row['name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
