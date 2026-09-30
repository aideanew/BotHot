#!/usr/bin/env bash
# BotHot 落库加密主密钥轮换（W7，2026-09-30）
#
# 配套规程：docs/07_release/key-rotation-sop.md（**先读它再动这个脚本**）
#
# ── 为什么需要这个脚本 ────────────────────────────────────────────────────────
# 本仓有两个「落库加密主密钥」：
#   PUSH_SECRET_MASTER_KEY   → bot_channels.secret_enc        （AAD = channel id）
#   ENGINE_KEY_MASTER_KEY    → engine_key_registrations.secret_ref（AAD = engine 名）
#
# ⚠️ 关键事实（读源码实证，非推测）：这两套密钥是**单密钥、无版本化 keyring** 的
#    （core/secret_crypto.py / core/engine_keyring.py 各自只有一个 master）。
#    因此「只改 env、不重加密存量密文」的后果不是"旧数据退化为明文"，而是
#    **旧密文全部永久不可解**——解密路径 fail-closed，抛 RequestInvalidError：
#      · 渠道密钥不可解 → 飞书/钉钉加签失效 → 该渠道投递全拒（push_scheduler.py:183）
#      · 引擎 Key 不可解 → 该引擎状态被报成"未配置"（engine_keys.py:89）
#    所以轮换 = 「换密钥」+「把存量密文用新密钥重加密」，两件事必须一起做完。
#    本脚本的存在就是为了把第二件事变成一条可执行、可回滚、默认不落地的命令。
#
# ── 安全设计（不可协商） ──────────────────────────────────────────────────────
# 1. 默认 dry-run：不带 --apply 时**零写入**（不碰数据库、不写任何文件）。
#    破坏性操作绝不能是"默认行为"，必须是显式选择。
# 2. 先备份后改写：--apply 第一步就把受影响密文导出为 JSON 快照（配合旧密钥即可回滚），
#    备份失败即整轮中止。
# 3. 单事务：两类密文的重加密在同一个事务里完成，要么全成要么全回滚，
#    绝不留下"渠道换了、引擎没换"的半轮换状态。
# 4. 不打印任何明文/密钥值：只打印 id、行数、状态。密钥只写入待审阅的 env 产物文件。
# 5. 不直接改 .env：脚本产出 `.env.rotated-<ts>` 供人工审阅替换（改环境文件是运维动作，
#    由脚本静默改写会造出"密钥换了但没人知道"的形态）。
#
# ── 用法 ─────────────────────────────────────────────────────────────────────
#   bash scripts/rotate_keys.sh                      # 计划（默认，零写入）
#   bash scripts/rotate_keys.sh --verify             # 只读校验：当前 env 密钥能否解开全部存量密文
#   bash scripts/rotate_keys.sh --apply              # 执行重加密轮换（自动生成新密钥）
#   bash scripts/rotate_keys.sh --generate push      # 只生成一个新主密钥并打印（push|engine）
#   bash scripts/rotate_keys.sh --help
#
# 环境变量：
#   DATABASE_URL               必填（--plan/--verify/--apply）。与后端同一 DSN。
#   PUSH_SECRET_MASTER_KEY     当前部署的渠道主密钥（--verify 只用它，见下方取舍说明）
#   ENGINE_KEY_MASTER_KEY      当前部署的引擎主密钥（同上）
#   OLD_PUSH_SECRET_MASTER_KEY **仅 --apply 生效**：存量密文当初所用的旧密钥；
#                              缺省 = 当前 PUSH_SECRET_MASTER_KEY
#   OLD_ENGINE_KEY_MASTER_KEY  同上（引擎侧）
#   NEW_PUSH_SECRET_MASTER_KEY --apply 时的新密钥；缺省自动生成
#   NEW_ENGINE_KEY_MASTER_KEY  同上
#   PYTHON                     Python 解释器覆盖（需同时具备 sqlalchemy / cryptography / backend 包）
#                              缺省依次尝试 backend/.venv/Scripts/python.exe → .venv/bin/python → python
#   BACKUP_DIR                 备份与产物目录；缺省 <repo>/key-rotation-backups
#                              （该目录由本脚本内置 `*` 规则自我忽略，产物永不可被 git 收录；
#                               生产环境请显式指向仓库外，如 /var/backups/bothot）
#   ROTATE_REFRESH_KEY_ID      缺省 1：轮换时一并刷新 engine_key_registrations.key_id
#                              （它是"轮换/审计句柄"，服务层每次覆盖登记都会换新，
#                               密文变了而句柄不变会让审计链路指错版本）。置 0 保留旧值。
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="plan"
GENERATE_TARGET=""

while [ $# -gt 0 ]; do
  case "$1" in
    --apply)    MODE="apply" ;;
    --verify)   MODE="verify" ;;
    --plan|--dry-run) MODE="plan" ;;
    --generate)
      MODE="generate"
      shift
      GENERATE_TARGET="${1:-push}"
      ;;
    -h|--help)  MODE="help" ;;
    *)
      echo "❌ 未知参数：$1" >&2
      echo "   用法见：bash scripts/rotate_keys.sh --help" >&2
      exit 1
      ;;
  esac
  shift
done

if [ "$MODE" = "help" ]; then
  sed -n '/^# ── 用法/,/^set -uo/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' | sed '$d'
  exit 0
fi

# ── Python 解释器（与 scripts/preflight.sh 同口径：优先项目 venv） ────────────
# PYTHON 环境变量可显式覆盖：运维/CI 里 venv 未必在约定位置，而本脚本需要
# sqlalchemy + cryptography + backend 包三者同时可用——让"用哪个解释器"可指定，
# 比让使用者去猜为什么 "No module named sqlalchemy" 更省事。
if [ -n "${PYTHON:-}" ]; then
  PY="$PYTHON"
elif [ -x "$ROOT/backend/.venv/Scripts/python.exe" ]; then
  PY="$ROOT/backend/.venv/Scripts/python.exe"
elif [ -x "$ROOT/backend/.venv/bin/python" ]; then
  PY="$ROOT/backend/.venv/bin/python"
else
  PY=python
fi

# ── generate 模式：纯本地生成，不碰数据库、不必有 DATABASE_URL ────────────────
if [ "$MODE" = "generate" ]; then
  case "$GENERATE_TARGET" in
    push)   VAR="PUSH_SECRET_MASTER_KEY" ;;
    engine) VAR="ENGINE_KEY_MASTER_KEY" ;;
    *) echo "❌ --generate 仅接受 push | engine，实际：$GENERATE_TARGET" >&2; exit 1 ;;
  esac
  # 32 字节 os.urandom 的 base64 —— 与 core/secret_crypto.py / engine_keyring.py 的
  # _KEY_BYTES=32 严格一致（生成侧与校验侧同一个数字，不各写一遍）。
  value="$("$PY" -c 'import base64,os;print(base64.b64encode(os.urandom(32)).decode())')" || {
    echo "❌ 生成失败：python 不可用（$PY）" >&2; exit 1; }
  echo "# 新主密钥（32 字节 base64）。⚠️ 这就是密钥本身——只粘贴到密钥管理系统/环境文件，"
  echo "#   不要进 git、不要进聊天记录、不要进 CI 日志。"
  echo "$VAR=$value"
  exit 0
fi

# DATABASE_URL 是 plan/verify/apply 的共同前置。缺它直接失败——绝不猜一个默认 DSN：
# 猜错的后果是"对生产库跑了计划"或更糟。
if [ -z "${DATABASE_URL:-}" ]; then
  echo "❌ 未设置 DATABASE_URL。" >&2
  echo "   示例：DATABASE_URL='postgresql+psycopg://bothot:bothot@127.0.0.1:5543/bothot' bash scripts/rotate_keys.sh" >&2
  exit 1
fi

# 仪表盘：先让操作者看清"这次要动什么、默认不落地"。
echo "════════════════════════════════════════════════════════════════"
echo " BotHot 主密钥轮换"
echo " 模式        : $MODE"
case "$MODE" in
  plan)   echo " 写入        : ❌ 无（dry-run 默认；要真执行请显式加 --apply）" ;;
  verify) echo " 写入        : ❌ 无（只读校验）" ;;
  apply)  echo " 写入        : ⚠️  会重写 bot_channels.secret_enc + engine_key_registrations.secret_ref（单事务）" ;;
esac
echo " 数据库      : $DATABASE_URL"
echo " Python      : $PY"
echo "════════════════════════════════════════════════════════════════"

# 切到 backend 目录：Python 侧要 `import app.core.secret_crypto`（包在 backend 下）。
cd "$ROOT/backend" || { echo "❌ 无法进入 $ROOT/backend" >&2; exit 1; }

ROTATE_MODE="$MODE" "$PY" - <<'PY'
"""轮换主体。

为什么复用 backend 自己的加解密函数（而不是在脚本里再写一遍 AES-GCM）：
  密文格式（b64(nonce).b64(ct+tag)）+ AAD 绑定（channel id / engine 名）是**契约**，
  在第二个地方重新实现一遍，等于让"轮换脚本"和"运行时解密"各有一份格式定义——
  这两份一旦漂移，症状是"轮换后密钥全不可解"，而那时旧密钥可能已经销毁。
  所以这里显式传 master= 复用同一份实现：格式只有一处定义。
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

MODE = os.environ["ROTATE_MODE"]

# ── 密钥解析（与 core/*.py 同纪律：32 字节 base64，畸形一律拒绝，绝不回落） ───
KEY_BYTES = 32


def decode_key(label: str, raw: str) -> bytes:
    if not raw:
        raise SystemExit(f"❌ {label} 缺失")
    try:
        key = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        raise SystemExit(f"❌ {label} 不是合法 base64")
    if len(key) != KEY_BYTES:
        raise SystemExit(f"❌ {label} 需 {KEY_BYTES} 字节（AES-256），实际 {len(key)} 字节")
    return key


def new_key() -> str:
    return base64.b64encode(os.urandom(KEY_BYTES)).decode()


old_push_raw = os.environ.get("OLD_PUSH_SECRET_MASTER_KEY") or os.environ.get("PUSH_SECRET_MASTER_KEY", "")
old_engine_raw = os.environ.get("OLD_ENGINE_KEY_MASTER_KEY") or os.environ.get("ENGINE_KEY_MASTER_KEY", "")

# ── 「解密用哪把密钥」的取舍：两种模式问的**不是同一个问题**，故取法不同 ──────
#   verify：问的是「**当前部署的**密钥能不能解开存量密文」——这是一次部署健康检查，
#           结论必须对应"此刻线上跑着的那把密钥"。若这里也认 OLD_*，
#           环境里一把陈旧的 OLD_* 就能让校验答成另一个问题：报 FAIL（明明线上没问题）
#           或报 OK（明明线上解不开）都发生过——校验的全部价值就在于"结论对应当前部署"。
#   apply ：问的是「库里那份密文是**用哪把钥匙**上的」——它可能已经不等于 env 里的值
#           （恢复场景：env 已换成新密钥，库还停在旧密钥）。此时必须能显式指定，
#           显式指定胜过错觉式的"应该就是 env 那个"。
LIVE_PUSH_SRC = "PUSH_SECRET_MASTER_KEY（当前部署）"
LIVE_ENGINE_SRC = "ENGINE_KEY_MASTER_KEY（当前部署）"
OVERRIDE_PUSH_SRC = "OLD_PUSH_SECRET_MASTER_KEY（显式覆盖）"
OVERRIDE_ENGINE_SRC = "OLD_ENGINE_KEY_MASTER_KEY（显式覆盖）"

if MODE == "verify":
    cur_push_raw, cur_push_src = os.environ.get("PUSH_SECRET_MASTER_KEY", ""), LIVE_PUSH_SRC
    cur_engine_raw, cur_engine_src = os.environ.get("ENGINE_KEY_MASTER_KEY", ""), LIVE_ENGINE_SRC
else:
    cur_push_raw = old_push_raw
    cur_push_src = OVERRIDE_PUSH_SRC if os.environ.get("OLD_PUSH_SECRET_MASTER_KEY") else LIVE_PUSH_SRC
    cur_engine_raw = old_engine_raw
    cur_engine_src = OVERRIDE_ENGINE_SRC if os.environ.get("OLD_ENGINE_KEY_MASTER_KEY") else LIVE_ENGINE_SRC

# ── 依赖导入 ────────────────────────────────────────────────────────────────
try:
    from sqlalchemy import create_engine, text
except ImportError as exc:  # pragma: no cover
    raise SystemExit(f"❌ 缺 sqlalchemy（{exc}）。请在 backend 环境内运行本脚本。")

from app.core.engine_keyring import decrypt_secret, encrypt_secret
from app.core.secret_crypto import (
    decrypt_channel_secret,
    decrypt_legacy_base64,
    encrypt_channel_secret,
    is_aes_ciphertext,
)

DSN = os.environ["DATABASE_URL"]
BACKUP_DIR = Path(os.environ.get("BACKUP_DIR") or Path.cwd().parent / "key-rotation-backups")

# 自保护：这两个产物是**密钥本身**与**密文快照**，最危险的落点就是被人 `git add .` 带进仓库。
# 仓库根 .gitignore 只有 `.env` / `.env.local`，`.env.rotated-<ts>` **不匹配**其中任何一条
# （gitignore 的 `.env` 只匹配同名文件，不匹配前缀）——靠"记得别提交"是纪律，不是机制。
# 故产物一律写进本目录，并在本目录内置一条 `*` 规则：本目录下任何文件都不可被 git 收录，
# 机制优先于纪律。`.gitignore` 自身也在 `*` 之内（本目录整体不出现在 git 视野里）。
IGNORE_FILE = BACKUP_DIR / ".gitignore"
REFRESH_KEY_ID = os.environ.get("ROTATE_REFRESH_KEY_ID", "1") != "0"
STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

engine = create_engine(DSN, future=True)


# ── 读取存量 ────────────────────────────────────────────────────────────────
def load_channels(conn):
    return conn.execute(
        text(
            "SELECT id, secret_enc FROM bot_channels "
            "WHERE secret_enc IS NOT NULL AND secret_enc <> '' ORDER BY id"
        )
    ).fetchall()


def load_engine_keys(conn):
    return conn.execute(
        text("SELECT engine, secret_ref, key_id FROM engine_key_registrations ORDER BY engine")
    ).fetchall()


with engine.connect() as conn:
    channels = load_channels(conn)
    engine_rows = load_engine_keys(conn)

legacy_n = sum(1 for _, ref in channels if not is_aes_ciphertext(ref))

print("── 存量盘点 ──────────────────────────────────────────────")
print(f"  bot_channels.secret_enc 非空行      : {len(channels)}（其中旧式 base64 明文 {legacy_n} 行）")
print(f"  engine_key_registrations 行        : {len(engine_rows)}")
print(f"  解密所用渠道密钥                   : {cur_push_src}")
print(f"  解密所用引擎密钥                   : {cur_engine_src}")
print(f"  刷新 key_id                        : {'是' if REFRESH_KEY_ID else '否'}")
print("──────────────────────────────────────────────────────────")

# ══════════════════════════════════════════════════════════════════════════
# plan（dry-run）—— 只报告，零写入
# ══════════════════════════════════════════════════════════════════════════
if MODE == "plan":
    print("\n[DRY-RUN] 不做任何写入。若执行 --apply，将依次发生：")
    print(f"  1. 导出密文快照（JSON）→ {BACKUP_DIR}/keys-backup-<ts>.json")
    print(f"  2. 单事务内重加密 {len(channels)} 行 bot_channels.secret_enc"
          f"（AAD 保持 = 各行 id，不解密输出、不打印明文）")
    print(f"  3. 单事务内重加密 {len(engine_rows)} 行 engine_key_registrations.secret_ref"
          f"（AAD 保持 = 各行 engine）")
    if REFRESH_KEY_ID:
        print(f"  4. 同步刷新 {len(engine_rows)} 行 key_id（轮换/审计句柄）")
    print(f"  5. 新密钥写入 {BACKUP_DIR}/env.rotated-<ts>（供人工审阅替换，不直接改 .env）")
    print("\n  ⚠️ 换成新密钥后，**旧的 .env 与旧密钥立即失效**；")
    print("     随后必须滚动重启 backend / scheduler / worker 三进程，否则新旧混用会出现")
    print("     「一部分进程能解、另一部分解不了」的分裂状态。步骤见：")
    print("     docs/07_release/key-rotation-sop.md")
    print("\n  若只想确认「当前 env 密钥能否解开全部存量密文」，跑 --verify。")
    raise SystemExit(0)

# ══════════════════════════════════════════════════════════════════════════
# verify —— 只读校验：当前 env 密钥是否与存量密文匹配
# ══════════════════════════════════════════════════════════════════════════
if MODE == "verify":
    try:
        master_push = decode_key("PUSH_SECRET_MASTER_KEY", cur_push_raw)
        master_engine = decode_key("ENGINE_KEY_MASTER_KEY", cur_engine_raw)
    except SystemExit as exc:
        print(exc)
        raise SystemExit(1)

    ok_ch = fail_ch = 0
    for cid, ref in channels:
        try:
            if is_aes_ciphertext(ref):
                decrypt_channel_secret(cid, ref, master=master_push)
            elif decrypt_legacy_base64(ref) is None:
                raise ValueError("legacy base64 不可解")
            ok_ch += 1
        except Exception:
            fail_ch += 1
            print(f"  ❌ 渠道 {cid} 不可解")

    ok_ek = fail_ek = 0
    for name, ref, _key_id in engine_rows:
        try:
            decrypt_secret(name, ref, master_engine)
            ok_ek += 1
        except Exception:
            fail_ek += 1
            print(f"  ❌ 引擎 {name} 不可解")

    print(f"\n渠道密钥：可解 {ok_ch} / 不可解 {fail_ch}")
    print(f"引擎 Key：可解 {ok_ek} / 不可解 {fail_ek}")
    if fail_ch or fail_ek:
        print("\n❌ 存在不可解密文——说明当前 env 密钥**不是**当初加密它们的那把。")
        print("   先找回正确的旧密钥再谈轮换（场景与处置见 key-rotation-sop.md「回滚」章）。")
        raise SystemExit(1)
    print("\n✅ 当前 env 密钥可解开全部存量密文，轮换前置条件成立。")
    raise SystemExit(0)

# ══════════════════════════════════════════════════════════════════════════
# apply —— 真正执行
# ══════════════════════════════════════════════════════════════════════════
assert MODE == "apply"

master_push = decode_key("PUSH_SECRET_MASTER_KEY（旧）", cur_push_raw)
master_engine = decode_key("ENGINE_KEY_MASTER_KEY（旧）", cur_engine_raw)

new_push_raw = os.environ.get("NEW_PUSH_SECRET_MASTER_KEY") or new_key()
new_engine_raw = os.environ.get("NEW_ENGINE_KEY_MASTER_KEY") or new_key()
new_push = decode_key("NEW_PUSH_SECRET_MASTER_KEY", new_push_raw)
new_engine = decode_key("NEW_ENGINE_KEY_MASTER_KEY", new_engine_raw)

# 同一个密钥"轮换"成自己 = 什么都没做，却会写一次库 + 让人以为已经换过。
# 这是最危险的假动作（心理上以为已处置，实际仍是泄露的那把），必须硬拦。
if new_push == master_push or new_engine == master_engine:
    raise SystemExit("❌ 新密钥与旧密钥相同——拒绝执行（这会给出「已轮换」的假象）")

BACKUP_DIR.mkdir(parents=True, exist_ok=True)
# 每条 apply 都重写一次（幂等）：即使目录是别人建的、或规则被误删，也立刻补回。
IGNORE_FILE.write_text("# 本目录存放密钥与密文快照，一律不得进 git（rotate_keys.sh 自动生成）\n*\n", encoding="utf-8")
backup_path = BACKUP_DIR / f"keys-backup-{STAMP}.json"

# ── 步骤 1：备份（先备份后改写，失败即整轮中止） ────────────────────────────
backup = {
    "created_at": STAMP,
    "dsn_host": DSN.rsplit("@", 1)[-1],  # 只记 host/db，不记凭据
    "note": "密文快照。配合 OLD_PUSH_SECRET_MASTER_KEY / OLD_ENGINE_KEY_MASTER_KEY 可回滚。",
    "bot_channels": [{"id": cid, "secret_enc": ref} for cid, ref in channels],
    "engine_key_registrations": [
        {"engine": name, "secret_ref": ref, "key_id": kid} for name, ref, kid in engine_rows
    ],
}
backup_path.write_text(json.dumps(backup, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"✅ 步骤 1 备份完成：{backup_path}（{backup_path.stat().st_size} 字节）")

# ── 步骤 2/3/4：单事务重加密 ────────────────────────────────────────────────
new_channel_refs: list[tuple[str, str]] = []
new_engine_refs: list[tuple[str, str, str]] = []

for cid, ref in channels:
    if is_aes_ciphertext(ref):
        plaintext = decrypt_channel_secret(cid, ref, master=master_push)
    else:
        # 旧式 base64（is_aes_ciphertext=False）：历史存量，借轮换顺手升级为 AES 密文。
        plaintext = decrypt_legacy_base64(ref)
        if plaintext is None:
            raise SystemExit(f"❌ 渠道 {cid} 的旧式密文无法解析，中止（库内零改动）")
    new_channel_refs.append((cid, encrypt_channel_secret(cid, plaintext, master=new_push)))

for name, ref, _kid in engine_rows:
    plaintext = decrypt_secret(name, ref, master_engine)
    new_engine_refs.append(
        (name, encrypt_secret(name, plaintext, master=new_engine), uuid.uuid4().hex)
    )

with engine.begin() as conn:  # engine.begin() = 单事务，异常自动回滚
    for cid, new_ref in new_channel_refs:
        conn.execute(
            text("UPDATE bot_channels SET secret_enc = :v WHERE id = :i"),
            {"v": new_ref, "i": cid},
        )
    for name, new_ref, new_kid in new_engine_refs:
        if REFRESH_KEY_ID:
            conn.execute(
                text(
                    "UPDATE engine_key_registrations SET secret_ref = :v, key_id = :k "
                    "WHERE engine = :e"
                ),
                {"v": new_ref, "k": new_kid, "e": name},
            )
        else:
            conn.execute(
                text("UPDATE engine_key_registrations SET secret_ref = :v WHERE engine = :e"),
                {"v": new_ref, "e": name},
            )

print(f"✅ 步骤 2/3/4 完成（单事务）：渠道 {len(new_channel_refs)} 行 + 引擎 {len(new_engine_refs)} 行已重加密")

# ── 步骤 5：产出待审阅的 env 文件（不直接改 .env） ──────────────────────────
env_out = BACKUP_DIR / f"env.rotated-{STAMP}"
env_out.write_text(
    "# 由 scripts/rotate_keys.sh 于 " + STAMP + " 生成。\n"
    "# 用途：替换部署环境中的同名变量，然后滚动重启 backend / scheduler / worker。\n"
    "# ⚠️ 本文件含密钥本身——替换完成后立即删除，且不得进 git（.gitignore 已覆盖 .env*）。\n"
    f"PUSH_SECRET_MASTER_KEY={new_push_raw}\n"
    f"ENGINE_KEY_MASTER_KEY={new_engine_raw}\n",
    encoding="utf-8",
)
try:
    env_out.chmod(0o600)
except OSError:
    pass  # Windows 上 chmod 语义有限，失败不阻断（但会提示）

print(f"✅ 步骤 5 完成：新密钥写入 {env_out}（权限 0600 尽力而为）")

print("\n── 后续人工步骤（脚本刻意不做） ──────────────────────────")
print(f"  1. 审阅并替换部署环境密钥：{env_out}")
print("  2. 滚动重启三进程：backend / scheduler / worker（缺一不可，否则新旧混用）")
print("  3. 重启后跑 `rotate_keys.sh --verify` 与一次真实渠道投递，确认解密路径正常")
print("  4. 确认无误后：删除 .env.rotated-* 与本次备份；销毁旧密钥的所有副本")
print("  5. 完整清单见 docs/07_release/key-rotation-sop.md")
print("\n⚠️ 备份文件是密文快照——旧密钥一旦销毁，它就没有回滚价值，只剩泄露面，一并清理。")
PY

exit $?
