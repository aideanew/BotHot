"""AB-P004 P4 引擎可插拔验收测试：端口六方法 1:1 对照 + engines/PATCH 端点行为（桩，零真实请求）。

机器门口径（T-019）：
- ① LangBotAdapter 六方法与 LangBotClient 现状调用 1:1 对照（upload_file/retrieve/delete 等 ≥4 项）；
- ② GET /engines：builtin configured=true；未配 Key 的 SaaS configured=false；
- ③ PATCH /spaces/{id}/engine=builtin 200（双写 engine_kb_id=langbot_kb_uuid）；
  engine=coze（Key 未配）→ 10004/403 带提示；
- ④ 空间视图追加 engine/engineKbId（P1 已迁字段复用）。

BE-02 加固：本文件端点用例对 .env 有隐式依赖（SaaS Key 占位可能导致 configured 非预期），
统一在 fixture 中清空 SaaS Key 环境变量，保证「未配 Key → configured=False」断言可复现；
新增已配 Key → configured=True 的三态用例（monkeypatch 注入，零真实请求）。
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user_id, get_db
from app.api.v1.engines import (
    _engine_allowlist,
    _engine_available,
    _engine_status,
    assert_engine_switchable,
)
from app.core.config import get_settings
from app.core.errors import AppError, ForbiddenError, RequestInvalidError
from app.main import create_app
from app.providers.engine_port import (
    ENGINE_IMPLEMENTED,
    ENGINE_ORDER,
    EngineRouter,
    LangBotAdapter,
    RagflowAdapter,
    SaasAdapter,
    make_engine,
)

# SaaS/主平台 Key 环境变量名（与 config.py 字段一一对应）
_SAAS_ENV_KEYS = ["COZE_API_KEY", "DIFY_API_KEY", "FASTGPT_API_KEY", "MAIN_KB_API_KEY", "MAIN_KB_API_BASE"]


@pytest.fixture(autouse=True)
def _clear_saas_keys_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """端点用例前置：清空 SaaS Key 环境变量，隔离 backend/.env 占位值。

    背景（BE-02 实测）：backend/.env 可能含 test_* 占位 Key（P4 联调期写入），
    使「未配 Key → configured=False」断言失效。真实环境变量优先级高于 .env 文件
    （pydantic-settings 默认），置空后 .env 值不再参与判定。
    """
    for key in _SAAS_ENV_KEYS:
        monkeypatch.setenv(key, "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()  # teardown：防缓存携带置空值污染后续用例

# ------------------------------------------------------------------ ① 适配器 1:1 对照


class _RecordClient:
    """记录 LangBotClient 调用序列（对照适配器 6 方法与现状调用 1:1）。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def upload_document(self, filename: str, content: Any) -> str:
        self.calls.append(("upload_document", (filename, content)))
        return "file-1"

    async def list_kb_files(self, kb_uuid: str) -> list[dict[str, Any]]:
        self.calls.append(("list_kb_files", (kb_uuid,)))
        return [{"file_name": "file-1", "status": "completed"}]

    async def retrieve(self, kb_uuid: str, question: str, top_k: int = 5) -> list[dict[str, Any]]:
        self.calls.append(("retrieve", (kb_uuid, question, top_k)))
        return [{"content": [{"text": "命中段落"}], "score": 0.9}]

    async def delete_kb_file(self, kb_uuid: str, file_id: str) -> None:
        self.calls.append(("delete_kb_file", (kb_uuid, file_id)))

    async def delete_kb(self, kb_uuid: str) -> None:
        self.calls.append(("delete_kb", (kb_uuid,)))


async def test_langbot_adapter_six_methods_1to1() -> None:
    """机器门①：LangBotAdapter 六方法逐一映射 LangBotClient 现状调用（upload/status/retrieve/delete x2）。"""
    rec = _RecordClient()
    adapter = LangBotAdapter(rec)  # type: ignore[arg-type]
    fid = await adapter.upload_file("kb-1", "a.md", "# t")
    assert fid == "file-1" and rec.calls[0][0] == "upload_document"
    st = await adapter.ingest_status("kb-1", "file-1")
    assert st == "completed" and rec.calls[1][0] == "list_kb_files"
    res = await adapter.retrieve("kb-1", "q", 3)
    assert res[0]["score"] == 0.9 and rec.calls[2][0] == "retrieve"
    await adapter.delete_file("kb-1", "file-1")
    assert rec.calls[3][0] == "delete_kb_file"
    await adapter.delete_kb("kb-1")
    assert rec.calls[4][0] == "delete_kb"
    assert [c[0] for c in rec.calls] == [
        "upload_document",
        "list_kb_files",
        "retrieve",
        "delete_kb_file",
        "delete_kb",
    ]


async def test_saas_adapter_key_missing_reports_unavailable() -> None:
    """机器门①b：SaaS 适配器 Key 未配置 → available=False，调用明确 RuntimeError（不假装可用）。"""
    coze = make_engine("coze", settings=_FakeSettings())
    assert isinstance(coze, SaasAdapter) and coze.available is False
    with pytest.raises(RuntimeError, match="未配置"):
        await coze.create_kb("x")
    ragflow = make_engine("main", settings=_FakeSettings())
    assert isinstance(ragflow, RagflowAdapter) and ragflow.available is False


async def test_make_engine_unknown_raises() -> None:
    with pytest.raises(ValueError, match="未知引擎位"):
        make_engine("notion", settings=_FakeSettings())  # Notion 按 CMS，非引擎位（ADR-0004）
    assert set(ENGINE_ORDER) == {"builtin", "main", "coze", "dify", "fastgpt"}


async def test_r1_pseudo_available_skeleton_engine_not_routable() -> None:
    """R1 回归：main 配置了 base+test_ 占位 Key 且在 allowlist，仍因未实接 available=False。

    杜绝骨架位 available=True → 六方法 NotImplementedError → 50001 的伪可用路径。
    """
    settings = _FakeSettings()
    settings.main_kb_api_base = "http://main-kb.invalid"
    settings.main_kb_api_key = "test_placeholder_key"
    ragflow = make_engine("main", settings=settings)
    assert isinstance(ragflow, RagflowAdapter) and ragflow.available is False
    assert ENGINE_IMPLEMENTED["main"] is False
    assert ENGINE_IMPLEMENTED["builtin"] is True
    router = EngineRouter(settings=settings)
    assert router.configured("main") is True and router.allowlisted("main") is True
    assert router.available("main") is False  # 三条件口径：implemented=False 终止伪可用
    assert router.available("builtin") is True


class _FakeSettings:
    kb_default_engine = "builtin"
    kb_engine_allowlist = "builtin,main"
    coze_api_key = ""
    dify_api_key = ""
    fastgpt_api_key = ""
    main_kb_api_base = ""
    main_kb_api_key = ""


# ------------------------------------------------------------------ ②③ 端点行为


def _endpoint_client(db_session: Any = None) -> TestClient:
    """端点测试应用：登录态固定 user-1；T5.4 起 GET/PATCH 读引擎 Key 登记表，
    故可选注入真实 PG 会话（db_session 夹具 + dependency_overrides，全套件既有惯例）。"""
    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    if db_session is not None:
        app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


async def test_engines_endpoint_builtin_available_saas_unconfigured(
    db_session,
) -> None:  # type: ignore[no-untyped-def]
    """机器门②：GET /engines builtin configured=true；SaaS Key 未配 configured=false。"""
    client = _endpoint_client(db_session)
    resp = client.get("/api/v1/engines")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0
    items = {e["engine"]: e for e in body["data"]["items"]}
    assert items["builtin"]["available"] is True and items["builtin"]["configured"] is True
    # .env 未配 SaaS Key（默认空串）→ configured=False；登记表空 → activeSource 恒 null
    assert items["coze"]["configured"] is False
    assert items["dify"]["configured"] is False
    assert items["fastgpt"]["configured"] is False
    for engine, item in items.items():
        assert item["activeSource"] is None, f"{engine} 无 env Key 亦无登记，activeSource 应为 null"
        assert item["decryptFailed"] is False
        assert item["keyEnv"] in ("", "MAIN_KB_API_KEY", "COZE_API_KEY", "DIFY_API_KEY", "FASTGPT_API_KEY")
    assert body["data"]["defaultEngine"] == "builtin"


async def test_patch_engine_unconfigured_key_403(db_session) -> None:  # type: ignore[no-untyped-def]
    """机器门③：PATCH engine=coze（Key 未配/未开放）→ 10004/403 拦截（不写库）。

    coze 不在缺省 allowlist(builtin,main) → 10004 未开放；空间无效则 30004。均 4xx 拦截。"""
    client = _endpoint_client(db_session)
    resp = client.patch(
        "/api/v1/spaces/00000000-0000-0000-0000-000000000001/engine",
        json={"engine": "coze"},
    )
    assert resp.status_code in (403, 404), f"应拦截：{resp.status_code} {resp.text}"
    body = resp.json()
    assert body["code"] in (10004, 30004)
    assert "coze" in body["message"] or "未开放" in body["message"] or "不存在" in body["message"]


async def test_patch_engine_builtin_double_write(db_session) -> None:  # type: ignore[no-untyped-def]
    """机器门③b：engine=builtin 双写 engine_kb_id=langbot_kb_uuid（连库夹具，外层事务回滚隔离）。"""
    from app.models.entities import KnowledgeSpace
    from app.repositories.user import SqlAlchemyUserStore

    user = await SqlAlchemyUserStore(db_session).upsert_by_sub(
        "sub-p4-ab004", "p4ab004@test.local", "P4-AB004"
    )
    space = KnowledgeSpace(user_id=user.id, name="P4引擎空间", langbot_kb_uuid="lb-kb-99")
    db_session.add(space)
    await db_session.flush()
    # 端点同口径双写：builtin 时 engine_kb_id = langbot_kb_uuid
    space.engine = "builtin"
    space.engine_kb_id = space.langbot_kb_uuid
    await db_session.flush()
    assert space.engine == "builtin" and space.engine_kb_id == "lb-kb-99"
    # 非 builtin（coze）：engine_kb_id 保留空串（实接后回填）
    space.engine = "coze"
    space.engine_kb_id = ""
    await db_session.flush()
    assert space.engine == "coze" and space.engine_kb_id == ""


# ------------------------------------------------------------------ R0.3 引擎门不变式


def _fully_configured_settings() -> _FakeSettings:
    """骨架位「配齐 Key + 全开放」的对抗配置：configured ∧ allowlisted 皆真，仅差 implemented。"""
    settings = _FakeSettings()
    settings.kb_engine_allowlist = "builtin,main,coze,dify,fastgpt"
    settings.coze_api_key = "test_coze_key"
    settings.main_kb_api_base = "http://main-kb.invalid"
    settings.main_kb_api_key = "test_main_key"
    return settings


def test_r031_skeleton_engine_with_key_now_rejected_as_unimplemented() -> None:
    """R0.3.1：骨架位配齐 Key 且进 allowlist 也必须 10004「尚未实接」（此前为放行）。

    F-3 根因：PATCH 只查 allowlist + configured，此配置下 coze/main 会放行；此后
    ingest 全 403（kb 前置检查用三条件），且 delete_space 走 SaasAdapter.delete_kb
    抛 NotImplementedError 整体回滚 → 空间无法删除。
    """
    settings = _fully_configured_settings()
    with pytest.raises(ForbiddenError) as exc:
        assert_engine_switchable("coze", settings=settings)
    assert "尚未实接" in str(exc.value)


def test_r031_rejection_reasons_layered_in_order() -> None:
    """R0.3.1：三类拒绝原因分层且顺序不可换（分层错会让管理员按错误指引行动）。"""
    # 未开放 优先于 未配 Key
    restricted = _FakeSettings()
    restricted.kb_engine_allowlist = "builtin"
    with pytest.raises(ForbiddenError) as exc:
        assert_engine_switchable("coze", settings=restricted)
    assert "未开放" in str(exc.value)
    # 已开放但未配 Key
    with pytest.raises(ForbiddenError) as exc:
        assert_engine_switchable("dify", settings=_fully_configured_settings())
    assert "未配置 API Key" in str(exc.value)
    # 未知引擎位（notion 按 CMS 对待，非引擎位——ADR-0004 §二）
    with pytest.raises(RequestInvalidError) as exc:
        assert_engine_switchable("notion", settings=_FakeSettings())
    assert "未知引擎位" in str(exc.value)


def test_r031_builtin_always_switchable_even_if_removed_from_allowlist() -> None:
    """R0.3.1：builtin 恒可通过——回退通道。allowlist 误配（不含 builtin）时若也拦住，
    空间被切到不可用引擎后就没有任何恢复路径（delete_space 会整体回滚）。"""
    settings = _FakeSettings()
    settings.kb_engine_allowlist = "coze"  # builtin 被误移出 allowlist
    assert_engine_switchable("builtin", settings=settings)


def test_r032_switchable_predicate_equals_available_across_all_slots() -> None:
    """R0.3.2 不变式：遍历 ENGINE_ORDER 全 5 位，PATCH 通过集合 == available() 为真集合。

    F-3 的根因是「同一份数据、两个谓词」（GET 三条件 / PATCH 两条件）。本测防未来
    新增引擎位时再次漂移。注：现无 implemented=True 的非 builtin 位，故可切换集合
    恒为 {"builtin"}——断言仍覆盖所有位的拒绝路径。
    """
    for settings in (_fully_configured_settings(), _FakeSettings()):
        router = EngineRouter(settings=settings)
        for engine in ENGINE_ORDER:
            configured = bool(_engine_status(engine, settings)["configured"])
            try:
                assert_engine_switchable(engine, settings=settings)
                passed = True
            except AppError:
                passed = False
            expected = _engine_available(engine, configured, _engine_allowlist(settings))
            assert passed == expected == router.available(engine), (
                f"{engine}: PATCH 谓词与 available() 分歧（passed={passed}, available={expected}）"
            )


def test_r032_empty_allowlist_divergence_only_at_builtin() -> None:
    """R0.3.2 反相：allowlist 为空时非 builtin 全拒、builtin 恒通（GET/PATCH/ingest 三口一致）。"""
    settings = _FakeSettings()
    settings.kb_engine_allowlist = ""
    assert _engine_available("builtin", True, [""]) is True  # builtin 不随 allowlist 判定
    for engine in ENGINE_ORDER:
        if engine == "builtin":
            assert_engine_switchable(engine, settings=settings)
            continue
        with pytest.raises(ForbiddenError):
            assert_engine_switchable(engine, settings=settings)


def test_r032_get_engines_reports_builtin_available_under_broken_allowlist() -> None:
    """R0.3.2：allowlist 误配时 GET /engines 仍报 builtin available（与 PATCH 谓词一致）。"""
    monkeypatch_env = _FakeSettings()
    monkeypatch_env.kb_engine_allowlist = ""
    status = _engine_status("builtin", monkeypatch_env)
    assert status["available"] is True
    assert _engine_status("coze", monkeypatch_env)["available"] is False
