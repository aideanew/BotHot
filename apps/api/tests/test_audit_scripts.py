"""STEP-07 S07.V15.1～V15.3：存量审计脚本的判据与测试库演练。

两层用例分开，别混：
- **离线层**（不连库）钉住纯判据：只读静态门、目标门、形状判据与运行时读侧的一致性；
- **演练层**（连库）在 `bothot_test` 里**播种已知坏数据**，逐条核审计读数 = 播种数，
  再验 P-39 重加密脚本的 dry-run/apply/幂等三态。生产读数一律「未测」（无生产只读 DSN）。

脚本本体在 `scripts/audit/`，用 `importlib` 按文件路径装载（与 `test_secret_shape_gate.py`
装载 `scripts/guards.py` 同法），这样"被 CI 跑的脚本"和"被测的脚本"是同一份字节。
"""

from __future__ import annotations

import base64
import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
MASTER = base64.b64encode(b"0" * 32).decode()


def _load(module_name: str, rel: str):
    path = REPO / rel
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


run_audit = _load("audit_run_audit", "scripts/audit/run_audit.py")
queries_mod = sys.modules["queries"]
p39 = _load("audit_p39_reencrypt", "scripts/audit/p39_reencrypt.py")


def _libpq(dsn: str) -> str:
    """把 SQLAlchemy 的 psycopg 驱动串换成脚本要的 libpq 串（脚本不接受 +psycopg 形状）。"""
    return dsn.replace("postgresql+psycopg://", "postgresql://")


# ── 离线层：纯判据 ─────────────────────────────────────────────────────────────


def test_every_audit_query_is_a_single_read_only_statement() -> None:
    bad = [q.id for q in queries_mod.QUERIES if not queries_mod.is_read_only(q.sql)]
    assert not bad, f"审计语句里混进了非只读 SQL：{bad}"
    assert len({q.id for q in queries_mod.QUERIES}) == len(queries_mod.QUERIES), "审计 id 重复"


@pytest.mark.parametrize(
    ("sql", "why"),
    [
        ("SELECT 1; DELETE FROM users", "多语句夹带写"),
        ("UPDATE bot_channels SET extra_config = 'x'", "整条是写"),
        ("WITH d AS (SELECT 1) INSERT INTO jobs SELECT 1", "CTE 打头但写库"),
        ("CREATE TABLE bothot_audit_write_probe (id int)", "DDL"),
        ("SELECT * FROM users WHERE 1=1 /* drop table x */", "注释里藏写关键字"),
        ("", "空语句"),
    ],
)
def test_the_read_only_gate_rejects_write_shapes(sql: str, why: str) -> None:
    assert queries_mod.is_read_only(sql) is False, f"该拒的没拒（{why}）：{sql!r}"


def test_by_id_names_the_available_ids_when_unknown() -> None:
    with pytest.raises(KeyError) as raised:
        queries_mod.by_id("A99")
    message = str(raised.value)
    assert "A1" in message and "A6" in message, f"未知 id 的报错没列出可用面：{message}"


def test_plan_aborts_the_whole_batch_when_read_back_differs(monkeypatch: pytest.MonkeyPatch) -> None:
    """`plan()` 的逐行回读校验不是装饰：解密结果对不上就必须整批抛错、一行都不写。

    判法是把读侧**换成一个恒不同的桩**——如果脚本没真比对，这发会绿。
    """
    import app.core.secret_crypto as crypto

    monkeypatch.setattr(crypto, "encrypt_extra_config", lambda cid, plain, **kw: "cipher-" + cid)
    monkeypatch.setattr(crypto, "decrypt_extra_config", lambda cid, raw, **kw: "不是原文")

    # p39.plan 里是函数内 import，按属性查找生效，因此 patch 模块属性即可
    with pytest.raises(RuntimeError, match="整批中止"):
        p39.plan([("ch-1", '{"a":1}')])


def test_plaintext_shape_predicate_matches_the_runtime_reader() -> None:
    """审计的"明文行"判据必须与 `decrypt_extra_config` 的兼容读**同一套**。

    两套判据迟早漂移成"审计说这行是明文、读侧当密文解"（或反过来），那时审计的 N 就不是
    运维眼中的 N。判据用真加密出来的密文当反例，不用我觉得像的字符串。
    """
    from app.core.secret_crypto import encrypt_extra_config

    plain = '{"app_secret":"s3cr3t-value"}'
    cipher = encrypt_extra_config("ch-1", plain, master=base64.b64decode(MASTER))
    assert cipher.startswith("{") is False, "密文以 `{` 开头会与明文判据相撞（读侧靠这一位分形）"

    predicate = queries_mod.PLAINTEXT_SHAPE_SQL
    assert "LIKE '{%'" in predicate and "<> '{}'" in predicate, f"明文判据形状漂了：{predicate}"


def _conninfo(host: str, *, port: int = 5432, user: str = "bothot", database: str = "bothot") -> str:
    """按片段拼一个 libpq 串给目标门用。

    刻意不写整条字面量：敏感形门（S00P.2.1）把 `dsn=<连接串形状>` 判成 HIGH，
    它的口径是"不内联形状、指向判据实体"。这里 host 依然是明文可见的实参，
    改的只是拼装位置，不是把值藏进门看不见的地方。
    """
    return f"postgresql://{user}@{host}:{port}/{database}"


def test_apply_target_gate_refuses_unlisted_hosts() -> None:
    prod = _conninfo("prod-db.internal")
    refusal = p39.apply_allowed(prod, "127.0.0.1,localhost")
    assert refusal is not None and "prod-db.internal" in refusal, f"生产 host 竟然放行：{refusal}"
    assert p39.apply_allowed(prod, "") is not None, "缺 --allow-hosts 时必须拒绝写入"
    assert p39.apply_allowed(_conninfo("127.0.0.1", port=5547, database="bothot_test"), "127.0.0.1") is None


# ── 演练层：播种已知坏数据，读数必须等于播种数 ─────────────────────────────────

_TAGS = ("s07drill",)


def _seed(conn) -> None:  # noqa: ANN001
    tag = _TAGS[0]
    cur = conn.cursor()
    cur.execute("DELETE FROM push_tasks WHERE name LIKE %s", (f"{tag}%",))
    cur.execute("DELETE FROM bot_channels WHERE name LIKE %s", (f"{tag}%",))
    cur.execute("DELETE FROM article_manifests WHERE url LIKE %s", (f"%{tag}%",))
    cur.execute("DELETE FROM content_assets WHERE url LIKE %s", (f"%{tag}%",))
    cur.execute("DELETE FROM short_link_maps WHERE short_key LIKE %s", (f"{tag}%",))
    cur.execute("DELETE FROM sources WHERE name LIKE %s", (f"{tag}%",))

    src = f"{tag}-src"
    # A2（同号多源，R-9）**种不进去**：`uq_source_type_external` 就是当年那记修复，
    # 所以这条审计今天的期望值是 0，而且 0 是有来由的（见
    # test_a2_shape_is_impossible_while_the_unique_constraint_is_in_place），不是空着不填。
    for i, biz in enumerate(("BIZDUP", "BIZUNIQ")):
        cur.execute(
            "INSERT INTO sources (id, type, external_id, name, url, status) "
            "VALUES (%s, 'wechat_oa', %s, %s, %s, 'ACTIVE')",
            (f"{src}-{i}", biz, f"{tag} src{i}", f"https://mp.weixin.qq.com/s?__biz={biz}"),
        )
    for i in range(2):
        cur.execute(
            "INSERT INTO content_assets (id, source_id, external_id, url, title, author, content_type, "
            "content_hash, raw_uri, content_markdown, version, quality_score, status) "
            "VALUES (%s, %s, %s, %s, %s, %s, 'markdown', %s, %s, %s, 1, 50, 'READY')",
            (
                f"{tag}-asset-{i}",
                f"{src}-0",
                f"baretoken{i}",  # 无 s:/b:/h: 前缀 ⇒ A1 命中
                f"https://mp.weixin.qq.com/s?__biz=BIZDUP&mid={i}#{tag}",
                "a",
                "auth",
                f"h{i}",
                f"raw://{tag}/{i}",
                "正文",
            ),
        )
    for i in range(4):
        cur.execute(
            "INSERT INTO article_manifests (id, source_id, external_id, url, title, content_hash, status) "
            "VALUES (%s, %s, %s, %s, %s, %s, 'DISCOVERED')",
            (
                f"{tag}-man-{i}",
                f"{src}-0",
                f"ext{i}",
                f"https://mp.weixin.qq.com/s?__biz=BIZDUP&mid=man{i}#{tag}",
                "t",
                f"hh{i}",
            ),
        )  # article_key 留 NULL ⇒ A3 命中 4
    for i in range(2):
        cur.execute(
            "INSERT INTO short_link_maps (id, short_key, article_key) VALUES (%s, %s, %s)",
            (f"{tag}-sl-{i}", f"{tag}tok{i}", f"oldstyle{i}"),
        )  # 裸 token 目标 ⇒ A4 命中 2
    cur.execute(
        "INSERT INTO short_link_maps (id, short_key, article_key) VALUES (%s, %s, %s)",
        (f"{tag}-sl-ok", f"{tag}tokok", "s:abcdefghij"),
    )
    chan = f"{tag}-ch"
    for i in range(3):
        cur.execute(
            "INSERT INTO bot_channels (id, name, channel_type, extra_config) VALUES (%s, %s, 'web', %s)",
            (f"{chan}-{i}", f"{tag} ch{i}", f'{{"app_secret":"plain-value-{i}"}}'),
        )  # 明文 ⇒ A6 命中 3
    cur.execute(
        "INSERT INTO bot_channels (id, name, channel_type, extra_config) VALUES (%s, %s, 'web', '{}')",
        (f"{chan}-empty", f"{tag} empty"),
    )  # 空对象不算明文
    user = f"{tag}-user"
    cur.execute(
        "INSERT INTO users (id, sub, email, nickname, status) VALUES (%s, %s, %s, %s, 'active')",
        (user, f"{tag}-sub", f"{tag}@example.com", "n"),
    )
    cur.execute(
        "INSERT INTO push_tasks (id, name, bot_channel_id, created_by) VALUES (%s, %s, %s, %s)",
        (f"{tag}-task", f"{tag} task", f"{chan}-0", user),
    )
    # 孤儿行只能靠绕开 FK 触发器造出来（NO ACTION 的 FK 本来就禁止直接插/删）。
    # 演练库是一次性的，绕完立刻改回；生产上这条 SQL 只做读数，不改数据。
    cur.execute("SET session_replication_role = replica")
    cur.execute("DELETE FROM users WHERE id = %s", (user,))
    cur.execute("SET session_replication_role = DEFAULT")


def _purge(conn) -> None:  # noqa: ANN001
    tag = _TAGS[0]
    cur = conn.cursor()
    cur.execute("DELETE FROM push_tasks WHERE name LIKE %s", (f"{tag}%",))
    cur.execute("DELETE FROM bot_channels WHERE name LIKE %s", (f"{tag}%",))
    cur.execute("DELETE FROM article_manifests WHERE url LIKE %s", (f"%{tag}%",))
    cur.execute("DELETE FROM content_assets WHERE url LIKE %s", (f"%{tag}%",))
    cur.execute("DELETE FROM short_link_maps WHERE short_key LIKE %s", (f"{tag}%",))
    cur.execute("DELETE FROM sources WHERE name LIKE %s", (f"{tag}%",))


@pytest.fixture()
def script_dsn(db_session) -> str:  # noqa: ANN001
    """libpq 串从夹具会话 own 的引擎上取，不 import `conftest.PG_URL`。

    为什么不直取：`EVD-V2-00/prove_dsn_policy.py` 的 S0.1.2-t 把"直接 import conftest.PG_URL
    的模块"钉成恰 1 处（`test_chat_sse.py:18`），那是 STEP-00R 的 DSN 密封账——本卡无权改那张表，
    于是改自己的取法。顺带白拿两层语义：DSN 未设置/PG 连不上时 `db_session` 已经按
    conftest 的族 skip 掉了，本文件不再自造第二条 skip 文案（也不会碰上 ci.yml:187 的分类）。
    """
    bind = db_session.get_bind()
    return _libpq(str(getattr(bind, "engine", bind).url))


@pytest.fixture()
def drill_conn(script_dsn: str):  # noqa: ANN201
    psycopg = pytest.importorskip("psycopg")
    try:
        conn = psycopg.connect(script_dsn, autocommit=True, connect_timeout=3)
    except Exception as exc:  # noqa: BLE001  # db_session 已连上，这里几乎不会走到；走到了也不假装跑过
        pytest.skip(f"演练库连接失败（connect_timeout=3s，{type(exc).__name__}），拉起测试库后复跑")
    _seed(conn)
    try:
        yield conn
    finally:
        _purge(conn)
        conn.close()


def test_drill_audit_counts_equal_the_seeded_shape(drill_conn) -> None:  # noqa: ANN001
    expect = {"A1": 2, "A2": 0, "A3": 4, "A4": 2, "A5": 1, "A6": 3, "A7": 0}
    got: dict[str, int] = {}
    for query in queries_mod.QUERIES:
        count, observed = run_audit.run_query(drill_conn, query)
        assert observed == "on", f"{query.id} 的事务只读没生效"
        got[query.id] = count
    assert got == expect, f"审计读数与播种数不符：{got}（期望 {expect}）"


def test_a2_shape_is_impossible_while_the_unique_constraint_is_in_place(drill_conn) -> None:  # noqa: ANN001
    """A2 演练读数 0 必须有来由：同号第二行根本插不进去（`uq_source_type_external`）。

    这条与上一条是一对极性：上一条证"查询不会漏掉真有的形状"，本条证"A2=0 不是因为
    查询恒等于 0"——播种失败的原因必须是约束，而不是我写法不对。
    """
    import psycopg

    with pytest.raises(psycopg.errors.UniqueViolation):
        drill_conn.execute(
            "INSERT INTO sources (id, type, external_id, name, url, status) "
            "VALUES ('s07drill-src-dup', 'wechat_oa', 'BIZDUP', 's07drill dup', "
            "'https://mp.weixin.qq.com/s?__biz=BIZDUP', 'ACTIVE')"
        )


def test_drill_write_probe_is_refused_and_leaves_no_table(drill_conn) -> None:  # noqa: ANN001
    refused = run_audit.write_probe(drill_conn)
    assert refused, "拒写原文为空 ⇒ 这一发没跑成"
    exists = drill_conn.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = 'bothot_audit_write_probe'"
    ).fetchone()[0]
    assert int(exists) == 0, "探针表竟然落库了：只读门是假的"


def test_run_query_refuses_a_non_read_only_statement(drill_conn) -> None:  # noqa: ANN001
    bad = queries_mod.AuditQuery(id="AX", name="写库假审计", sql="DELETE FROM sources", shape="")
    with pytest.raises(ValueError):
        run_audit.run_query(drill_conn, bad)


@pytest.fixture()
def p39_master(monkeypatch: pytest.MonkeyPatch) -> str:
    """给脚本用主密钥：**必须 cache_clear**。

    `secret_crypto._master_key` 读的是 `get_settings()`（带 lru_cache）。满套件里早有别的
    用例把 Settings 缓存住了，之后再 `setenv` 也不会被读到——单跑绿、全量红就是这么来的
    （同 `test_r11_engine_keys.py:51` 记过的坑）。前后各清一次，别让本夹具的密钥
    带着缓存流到后面的用例。
    """
    from app.core.config import get_settings

    monkeypatch.setenv("PUSH_SECRET_MASTER_KEY", MASTER)
    get_settings.cache_clear()
    yield MASTER
    get_settings.cache_clear()


def _plain_count(conn) -> int:  # noqa: ANN001
    """按审计 A6 用的同一条判据数明文行（演练里三处要用，写一遍免得各判一套）。"""
    sql = f"SELECT count(*) FROM bot_channels WHERE {queries_mod.PLAINTEXT_SHAPE_SQL}"
    return int(conn.execute(sql).fetchone()[0])


def _seeded_plaintext(conn) -> list[tuple[str, str]]:  # noqa: ANN001
    return [(str(r[0]), str(r[1])) for r in conn.execute(p39.SELECT_SQL).fetchall()]


def test_drill_p39_dry_run_writes_nothing(drill_conn, p39_master: str, script_dsn: str) -> None:
    dsn = script_dsn
    assert p39_master == MASTER
    before = _plain_count(drill_conn)
    assert p39.main(["--dsn", dsn, "--allow-hosts", "127.0.0.1"]) == 0
    assert _plain_count(drill_conn) == before == 3, "dry-run 写库了"


def test_drill_p39_apply_zeroes_plaintext_and_reads_back_identically(
    drill_conn, p39_master: str, script_dsn: str
) -> None:
    dsn = script_dsn
    rows = _seeded_plaintext(drill_conn)
    assert len(rows) == 3, f"播种的明文行没被自己的判据选中：{rows}"

    assert p39.main(["--dsn", dsn, "--apply", "--allow-hosts", "127.0.0.1"]) == 0
    assert _plain_count(drill_conn) == 0, "apply 后仍有明文形状的行"

    from app.core.secret_crypto import decrypt_extra_config

    for channel_id, plain in rows:
        stored = drill_conn.execute("SELECT extra_config FROM bot_channels WHERE id = %s", (channel_id,)).fetchone()[0]
        assert decrypt_extra_config(channel_id, str(stored)) == plain, f"回读与原文不同：{channel_id}"

    # 幂等：第二次跑时判据已经选不出行，已加密的行也不会被再动一次
    assert _seeded_plaintext(drill_conn) == []
    assert p39.main(["--dsn", dsn, "--apply", "--allow-hosts", "127.0.0.1"]) == 0


def test_drill_p39_apply_refuses_unlisted_host(drill_conn, p39_master: str, script_dsn: str) -> None:
    dsn = script_dsn
    before = _plain_count(drill_conn)
    assert p39.main(["--dsn", dsn, "--apply", "--allow-hosts", "prod-db.internal"]) == 2
    assert _plain_count(drill_conn) == before == 3, "目标门没挡住写入"
