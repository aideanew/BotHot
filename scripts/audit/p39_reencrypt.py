#!/usr/bin/env python3
"""P-39 存量明文 `bot_channels.extra_config` 重加密（STEP-07 S07.V15.3）。

**默认 dry-run**；只有 `--apply` 才写库，而 `--apply` 还必须显式给出 `--allow-hosts`，
DSN 的 host 不在里面就直接停——这是"本脚本不执行于生产"的机械形式，
不靠人记住"这次别跑生产"。

加密口径**复用运行时那一套**（`app.core.secret_crypto.encrypt_extra_config/decrypt_extra_config`，
AAD = `{channel_id}:extra_config`），而不是照抄迁移 ab1005w5b 里的 AES 代码：
迁移是一次性历史工件，读侧才是长期真源；照抄迁移等于造第二套口径，
两套口径迟早会漂移成"写进去的解不出来"。

每行都先**加密→解密→逐字比对**通过才计入待发写；任何一行不过，整批中止（fail-closed）。
写完立刻复查审计查询 A6 的计数（应归 0）与每行的解密回读。
重复执行没有副作用：第二次跑时明文判据已经选不出行 ⇒ 待处理 0 行。

主密钥纪律与线上一致：缺失/畸形时 `encrypt_extra_config` 自己 fail-closed 抛错，
本脚本不代生密钥、不回落明文。

用法：
    python scripts/audit/p39_reencrypt.py --dsn ...                     # 只报告
    python scripts/audit/p39_reencrypt.py --dsn ... --apply --allow-hosts 127.0.0.1
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

API = Path(__file__).resolve().parents[2] / "apps" / "api"
sys.path.insert(0, str(API))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from queries import PLAINTEXT_SHAPE_SQL  # noqa: E402

SELECT_SQL = f"SELECT id, extra_config FROM bot_channels WHERE {PLAINTEXT_SHAPE_SQL} ORDER BY id"


def host_of(dsn: str) -> str:
    """从 libpq 连接串取 host（只用于目标门；不打印端口、用户或任何口令段）。"""
    import psycopg

    params = psycopg.conninfo.conninfo_to_dict(dsn)
    return str(params.get("host", "") or "localhost")


def apply_allowed(dsn: str, allow_hosts: str) -> str | None:
    """返回拒绝理由（None = 允许写）。这是 `--apply` 唯一的目标门。"""
    allowed = {item.strip() for item in allow_hosts.split(",") if item.strip()}
    if not allowed:
        return "--apply 需要同时给出 --allow-hosts（逗号分隔的白名单）；缺省一律拒绝写入"
    host = host_of(dsn)
    if host not in allowed:
        return f"DSN 的 host={host!r} 不在白名单 {sorted(allowed)} 内 ⇒ 拒绝写入（生产不在任何白名单里）"
    return None


def plan(rows: list[tuple[str, str]]) -> list[tuple[str, str, str]]:
    """把明文行算成 `(id, 明文, 密文)`，并逐行验证解密回读与原文逐字一致。

    任何一行不一致就抛错——半批写进库比一批都不写更糟。
    """
    from app.core.secret_crypto import decrypt_extra_config, encrypt_extra_config

    pending: list[tuple[str, str, str]] = []
    for channel_id, plain in rows:
        cipher = encrypt_extra_config(channel_id, plain)
        back = decrypt_extra_config(channel_id, cipher)
        if back != plain:
            raise RuntimeError(f"渠道 {channel_id} 的加解密回读不一致，整批中止（不写任何行）")
        pending.append((channel_id, plain, cipher))
    return pending


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    import psycopg

    if args.apply:
        refusal = apply_allowed(args.dsn, args.allow_hosts)
        if refusal:
            print(f"❌ {refusal}", file=sys.stderr)
            return 2

    with psycopg.connect(args.dsn, autocommit=False, connect_timeout=5) as conn:
        rows = [(str(r[0]), str(r[1])) for r in conn.execute(SELECT_SQL).fetchall()]
        pending = plan(rows)
        mode = "APPLY" if args.apply else "DRY-RUN"
        print(f"[{mode}] 明文行数={len(pending)}")
        for channel_id, plain, _cipher in pending:
            # 只报 id 与长度：extra_config 里是飞书 app_secret / 钉钉 access_token，正文一个字都不许进日志
            print(f"  {channel_id} 明文 {len(plain)} 字符（形状 {plain[:1]}'…'{plain[-1:]})")
        if not args.apply:
            print("[DRY-RUN] 未写库。要真的重加密请加 --apply --allow-hosts <host>")
            return 0
        for channel_id, _plain, cipher in pending:
            conn.execute(
                "UPDATE bot_channels SET extra_config = %s WHERE id = %s",
                (cipher, channel_id),
            )
        conn.commit()
        from app.core.secret_crypto import decrypt_extra_config

        count_row = conn.execute(f"SELECT count(*) FROM bot_channels WHERE {PLAINTEXT_SHAPE_SQL}").fetchone()
        remaining = int(count_row[0]) if count_row is not None else -1
        checked = 0
        for channel_id, plain, _cipher in pending:
            stored_row = conn.execute(
                "SELECT extra_config FROM bot_channels WHERE id = %s", (channel_id,)
            ).fetchone()
            if stored_row is None:
                print(f"❌ 渠道 {channel_id} 回读缺行", file=sys.stderr)
                return 2
            if decrypt_extra_config(channel_id, str(stored_row[0])) != plain:
                print(f"❌ 渠道 {channel_id} 写后回读不一致", file=sys.stderr)
                return 2
            checked += 1
        print(f"[APPLY] 已重写 {checked} 行；复查 A6 计数={remaining}（应为 0）")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="P-39 存量 extra_config 重加密（默认 dry-run）")
    parser.add_argument("--dsn", required=True, help="libpq 连接串（必填，脚本内无默认值）")
    parser.add_argument("--apply", action="store_true", help="真的写库（默认不写）")
    parser.add_argument("--allow-hosts", default="", help="--apply 时的 host 白名单（逗号分隔）")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
