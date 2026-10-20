"""存量审计的只读 SQL 集合（STEP-07 S07.V15.1 / V15.2）。

为什么要显式一张表而不是散在脚本里写字符串：判据要被单测钉住极性
（`apps/api/tests/test_audit_scripts.py`），而 SQL 一旦埋在 CLI 里就只能连库跑才有读数。

来源对应：
- A1/A2/A3/A4 = 来源卡 §1 的四项（裸 token 资产键、同号多源 R-9、清单键空值、短链映射目标形状），
  也是卡面『回填输入清单』的 1/2/3 号线；
- A5 = STEP-24 S24.3.1（`push_tasks.created_by` 指向已删用户）；
- A6 = P-39（`bot_channels.extra_config` 存量明文行）。

所有语句**只能是单条 SELECT**；`is_read_only()` 是硬门，不是注释。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 明文/密文形态判据的唯一真源：与运行时 `decrypt_extra_config` 的兼容读**同一条**规则
# （"{" 开头当明文）。审计与读侧若各判一套，就会出现"审计说有 N 行明文、读侧却当密文解"
# 或反之——那等于审计白做。
PLAINTEXT_SHAPE_SQL = "extra_config LIKE '{%' AND extra_config <> '{}'"

_WRITE_TOKENS = (
    "insert",
    "update",
    "delete",
    "merge",
    "create",
    "drop",
    "alter",
    "truncate",
    "grant",
    "revoke",
    "copy",
    "vacuum",
    "call",
    "do",
    "refresh",
    "comment",
    "lock",
    "set",
)


@dataclass(frozen=True)
class AuditQuery:
    id: str
    name: str
    sql: str
    shape: str
    """这条读数在**演练库**里的期望形状：`seed=<表达式>`，由用例按播种数核。"""


QUERIES: tuple[AuditQuery, ...] = (
    AuditQuery(
        id="A1",
        name="content_assets 裸 token 资产键（规范键迁移前的末段键）",
        sql=(
            "SELECT count(*) FROM content_assets "
            "WHERE external_id <> '' "
            "AND external_id NOT LIKE 's:%' AND external_id NOT LIKE 'b:%' AND external_id NOT LIKE 'h:%'"
        ),
        shape="D-V9-01/D-V9-03 播种的裸末段键行数",
    ),
    AuditQuery(
        id="A2",
        name="同号多源（同一 biz 落多条 sources，R-9）",
        sql=(
            "SELECT count(*) FROM (SELECT external_id FROM sources "
            "WHERE type = 'wechat_oa' AND external_id <> '' "
            "GROUP BY external_id HAVING count(*) > 1) dup"
        ),
        shape="重复 biz 的**组数**（不是行数）",
    ),
    AuditQuery(
        id="A3",
        name="article_manifests.article_key 空值行（D-V9-04 故意留 NULL）",
        sql="SELECT count(*) FROM article_manifests WHERE article_key IS NULL",
        shape="NULL 键行数（回填门槛：应从 >0 变 0）",
    ),
    AuditQuery(
        id="A4",
        name="short_link_maps 映射目标仍是裸 token（未升规范键）",
        sql=(
            "SELECT count(*) FROM short_link_maps "
            "WHERE article_key <> '' "
            "AND article_key NOT LIKE 's:%' AND article_key NOT LIKE 'b:%' AND article_key NOT LIKE 'h:%'"
        ),
        shape="旧短链映射行数",
    ),
    AuditQuery(
        id="A5",
        name="push_tasks.created_by 孤儿行（STEP-24 S24.3.1）",
        sql=(
            "SELECT count(*) FROM push_tasks t "
            "LEFT JOIN users u ON u.id = t.created_by "
            "WHERE t.created_by IS NOT NULL AND u.id IS NULL"
        ),
        shape="created_by 非空但 users 无此行的任务数",
    ),
    AuditQuery(
        id="A6",
        name="bot_channels.extra_config 明文行（P-39 存量）",
        sql=f"SELECT count(*) FROM bot_channels WHERE {PLAINTEXT_SHAPE_SQL}",
        shape="明文 JSON 行数（重加密后应为 0）",
    ),
    AuditQuery(
        id="A7",
        name="前导零形态的 b: 键（S2.4 之后新旧并存的候选）",
        sql=(
            "SELECT count(*) FROM ("
            "SELECT article_key AS k FROM article_manifests WHERE article_key LIKE 'b:%' "
            "UNION ALL "
            "SELECT external_id AS k FROM content_assets WHERE external_id LIKE 'b:%'"
            ") t WHERE split_part(t.k, ':', 3) LIKE '0%'"
        ),
        shape=(
            "`b:{biz}:{mid}:{idx}` 的 mid 段以 0 开头的**行数**（清单 + 资产两列合计）。"
            "S2.4 之后新行一律 `str(int(x))` 规范化，所以这里量的是历史并存行；"
            "实测为 0 也要写 0（卡面『回填输入清单』第 3 行的要求）"
        ),
    ),
)


def by_id(query_id: str) -> AuditQuery:
    for query in QUERIES:
        if query.id == query_id:
            return query
    raise KeyError(f"未知的审计查询 id：{query_id}（可用：{', '.join(q.id for q in QUERIES)}）")


def is_read_only(sql: str) -> bool:
    """单条 SELECT/WITH 才算只读；其余一律 False（含多语句拼接与以分号结尾夹带的写句）。"""
    text = sql.strip().rstrip(";").strip()
    if not text or ";" in text:
        return False
    if not re.match(r"^(select|with)\b", text, re.IGNORECASE):
        return False
    lowered = text.lower()
    # 关键字按**词界**匹配：`created`/`selected` 里含 `set`/`select` 之类子串不能误判，
    # 而 `; update ...` 这种夹带已经被上面的分号检查挡掉，这里再兜一层前向词界。
    return not any(re.search(rf"\b{token}\b", lowered) for token in _WRITE_TOKENS)
