"""STEP-33 S33.1：422（10005）的任何一处都不许把调用方提交的值带回去。

判据的形状（D-V18-05）：**只报字段路径 + 错误类型 + 原因**，`input` 与 `ctx` 一律不读。
旧实现是 `f"请求参数校验失败: {exc.errors()[:1]}"`——把整份错误字典格式化进 message，
而 pydantic 的字典里就有 `input`，于是调用方塞进来的凭据串被复制进响应体（也进了任何
把它记下来的日志）。本文件里所有"凭据形"的值都是**运行时随机生成**的，源码零凭据字面量。

为什么不写成连库用例：现读（EVD-V18-33 §1）证明 FastAPI **先解依赖、后校体**，
未认证提交非法体只会拿到 401/10001，泄漏面根本不可达；而三条真端点都要角色。
这里用桩会话覆盖 `get_db` 与 `get_current_user_id`（角色依赖 `require_role` 只调
`session.scalar(...)`，一个 `scalar` 方法就够），于是**不连库也能打到真实 URL 与真实处理器**。
好处有三：本机可复现先红、CI-Windows 的零余量 skip 基线不被抬起、用例与 PG 无关。
"""

from __future__ import annotations

import logging
import re
import secrets
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError, field_validator

from app.api.deps import get_current_user_id, get_db
from app.api.v1.admin import CategoryConfigRequest, DiscoveryConfigRequest
from app.api.v1.extract import ExtractRequest
from app.core.validation_message import build_validation_message
from app.main import create_app
from app.models.entities import User

ADMIN = "/api/v1/admin"


def _marker() -> str:
    """运行时随机值：长度与字符集都贴近真实令牌，但它不是任何凭据。"""
    return "tok-" + secrets.token_urlsafe(24)


class _StubSession:
    """只满足 `require_role` 的取行方式（`SqlAlchemyUserStore.get_by_id` 走 `session.scalar`）。

    刻意不提供 `execute`/`add`/`flush`：如果处理器真的开始跑端点本体（那会写库），
    这里会 AttributeError ⇒ 用例红，而不是静默地把桩扩成一个库。
    """

    def __init__(self, user: User) -> None:
        self._user = user

    async def scalar(self, _stmt: object) -> User:
        return self._user


def _client(role: str = "admin") -> TestClient:
    user = User(id="u-no-echo", sub="s-no-echo", email="probe@example.test", role=role)
    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: user.id
    app.dependency_overrides[get_db] = lambda: _StubSession(user)
    return TestClient(app, raise_server_exceptions=False)


# ─── 判据本体：三个卡面点名的真端点 ──────────────────────────────────────────────

# 每条 (方法, URL, 构造非法体的函数)：非法点都落在**类型**上，因此提交值必然进 `input`。
_REAL_ENDPOINTS = [
    ("PUT", f"{ADMIN}/discovery/config", lambda m: {"enabled": m, "default": "redfox"}),
    ("PUT", f"{ADMIN}/categories", lambda m: {"categories": m}),
    ("POST", "/api/v1/extract", lambda m: {"url": m + "z" * 600}),
]


@pytest.mark.parametrize(("method", "path", "build"), _REAL_ENDPOINTS)
def test_real_endpoints_never_echo_the_submitted_value(
    method: str, path: str, build: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """S33.1 的先红主判据：响应体与 caplog 全文都不含那个随机值。"""
    marker = _marker()
    client = _client()
    with caplog.at_level(logging.DEBUG):
        resp = client.request(method, path, json=build(marker))

    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body["code"] == 10005, body
    assert marker not in resp.text, "响应体把调用方提交的原值回显出来了"
    assert not any(marker in record.getMessage() for record in caplog.records), "日志回显了原值"
    # data 位也必须在判据面上（旧实现只挪了 message，`data` 里塞整份 errors 同样泄漏）
    assert marker not in repr(body["data"]), "data 位回显了原值"


def test_field_name_chosen_by_the_caller_is_not_a_leak_channel() -> None:
    """`extra="forbid"` 的 loc 里带着**调用方起的字段名**——那同样是调用方控制的文本。

    把凭据串当键名提交（`{"<tok>": 1}`），朴素实现会把它拼进"字段路径"照样回显。
    判据因此不是"不读 input 就完了"，而是"调用方能控制的文本一律不进 message"。
    """
    marker = _marker()
    resp = _client().put(f"{ADMIN}/discovery/config", json={marker: 1})
    assert resp.status_code == 422
    assert marker not in resp.text, "字段路径没做形状约束，调用方起的键名被原样拼进文案"


def test_message_still_names_the_field_and_the_type() -> None:
    """反向极性：修完不许把文案糊成一句空话。

    "不回显"最容易做成"什么都不说"——那既没判据价值，前端也没法本地化。
    这里钉住路径与类型仍然出现（`body.enabled` 与 `list_type`），且只出现一次冒号后的原因。
    """
    resp = _client().put(f"{ADMIN}/discovery/config", json={"enabled": 5, "default": "redfox"})
    assert resp.status_code == 422
    message = resp.json()["message"]
    assert "body.enabled" in message, message
    assert "list_type" in message, message


def test_multiple_errors_report_first_path_plus_a_count() -> None:
    """三条都非法 ⇒ 文案给第一条的路径与类型，并明确"另有几处"，不逐条铺开。"""
    resp = _client().put(
        f"{ADMIN}/discovery/config",
        json={"enabled": 5, "default": 5, "unexpected": 1},
    )
    assert resp.status_code == 422
    message = resp.json()["message"]
    assert "另有 2 处" in message, message


class _InterpolatingProbe(BaseModel):
    """模块级定义：本文件带 `from __future__ import annotations`，函数内定义的模型
    FastAPI 解析不到（注解是字符串），路由会退化成"另一种 422"而不是我要的那次校验失败。
    这是一条**假绿**的来源，不是实现细节。
    """

    value: str

    @field_validator("value")
    @classmethod
    def _reject(cls, v: str) -> str:
        raise ValueError(f"坏值 {v}")


def test_probe_route_with_a_custom_validator_does_not_leak_the_interpolated_msg() -> None:
    """pydantic 会把**自定义校验器的异常文本**放进 `msg` 与 `ctx`——那正是"msg 里含输入值"的真实形状。

    卡面 S33.2 明写这种类型要换成固定原因。这条用例喂的是一次真实的 ValidationError，
    并且先把前提钉住：pydantic 自己给的 `msg`/`ctx` 里确实带着原值（改前实测
    `msg='Value error, 坏值 <值>'`、`ctx={'error': ValueError('坏值 <值>')}`）。
    """
    marker = _marker()
    app = create_app()

    @app.post("/api/v1/system/_no_echo_probe")
    async def probe(payload: _InterpolatingProbe) -> dict[str, str]:
        return {"ok": payload.value}

    resp = TestClient(app, raise_server_exceptions=False).post(
        "/api/v1/system/_no_echo_probe", json={"value": marker}
    )
    assert resp.status_code == 422, resp.text
    with pytest.raises(ValidationError) as excinfo:
        _InterpolatingProbe.model_validate({"value": marker})
    errors = excinfo.value.errors()
    assert marker in str(errors), "这条用例的前提（msg/ctx 内插原值）已不成立 ⇒ 用例失去判定力"
    assert marker in str(errors[0].get("ctx")), "ctx 里没有原值 ⇒ 这条用例不再覆盖 ctx 形状"
    assert marker not in resp.text, resp.text


# ─── 处理器本体：手造错误字典的极性（不依赖 HTTP 也能判）──────────────────────────

def test_builder_ignores_input_and_ctx_even_when_they_hold_the_value() -> None:
    """`input`/`ctx` 里塞满原值也进不了文案——包括列表、字典、字节与"预期值"这类形状。"""
    marker = _marker()
    errors = [
        {
            "type": "value_error",
            "loc": ("body", "token"),
            "msg": f"坏值 {marker}",
            "input": marker,
            "ctx": {"error": marker, "expected": marker},
        },
        {
            "type": "list_type",
            "loc": ("body", "items", 0, "secret"),
            "msg": "Input should be a valid list",
            "input": [marker, {"k": marker}],
        },
        {"type": "json_invalid", "loc": ("body", 12), "msg": f"JSON input: {marker}", "input": marker},
    ]
    text = build_validation_message(errors)
    assert marker not in text, text
    assert "body.items.0.secret" in text or "body.token" in text, text
    assert "value_error" in text, text


def test_builder_survives_an_empty_error_list_without_crashing() -> None:
    """空 errors 是可达形状（`RequestValidationError([])`）；处理器不许 IndexError 变成 500。"""
    text = build_validation_message([])
    assert text and "10005" not in text  # 文案本身不带码，码由信封给
    assert "校验" in text, text


def test_builder_falls_back_for_unknown_types_without_using_msg() -> None:
    """没见过的新类型必须走固定原因——把 pydantic 的 msg 原样端出来就是把判据交给上游版本。"""
    marker = _marker()
    text = build_validation_message(
        [{"type": "brand_new_type", "loc": ("body", "field"), "msg": f"含值 {marker}", "input": marker}]
    )
    assert marker not in text, text
    assert "brand_new_type" in text, text


def test_the_detection_itself_is_proved_to_work() -> None:
    """判据的反证：如果处理器按旧写法拼，上面的用例必须能抓到。

    这一条不测生产代码，测的是**我的检测手段有没有判定力**——把旧实现原样复现一遍，
    断言 marker 确实出现在文本里。若哪天这条变绿，说明 marker 生成方式失效了
    （比如随机串太短撞不进 repr），整套用例就是在自欺。
    """
    marker = _marker()
    legacy = f"请求参数校验失败: {[{'type': 'list_type', 'loc': ('body', 'enabled'), 'msg': 'x', 'input': marker}]}"
    assert marker in legacy
    assert build_validation_message(
        [{"type": "list_type", "loc": ("body", "enabled"), "msg": "x", "input": marker}]
    ) not in legacy, "新文案与旧文案必须不同形，否则上面的断言没有区分力"


# ─── 覆盖面：三个真端点用的就是这些模型（防止"探针路由绿了、真端点没绿"）──────────

def test_the_probe_models_are_the_ones_the_real_routes_use() -> None:
    """`_REAL_ENDPOINTS` 的判据力来自"打到的是真路由"。这里用**公开面**钉住对应关系。

    不走 `app.routes` 的内部结构：现读 FastAPI 把 include 进来的路由包成
    `_IncludedRouter`（属性是 `original_router`，不是 `routes`），按内部属性爬依赖树
    会在一次版本升级后悄悄返回空集——空集在断言里看起来像"路径没了"，在别的写法里就像"全绿"。
    `openapi()["paths"]` 是对外契约面，路由不在里面就是真的不在。
    """
    paths = create_app().openapi()["paths"]
    for path, method in (
        (f"{ADMIN}/discovery/config", "put"),
        (f"{ADMIN}/categories", "put"),
        ("/api/v1/extract", "post"),
    ):
        assert path in paths, f"现读 OpenAPI 里没有 {path} ⇒ _REAL_ENDPOINTS 的前提已过期"
        assert method in paths[path], f"{path} 不再接受 {method}"
    # 类型约束确实落在模型里（不是靠端点本体的手写校验），否则"错误类型"这个判据面无从谈起
    assert "enabled" in DiscoveryConfigRequest.model_fields
    assert "categories" in CategoryConfigRequest.model_fields
    assert "url" in ExtractRequest.model_fields


def test_no_error_dict_is_stringified_into_the_handler_source() -> None:
    """卡面完成判据第 2 条的常驻版：`main.py` 里不许再把整份 errors 格式化进 message。

    文本级检查（不是运行级）：运行级用例只覆盖我构造过的形状，
    而"把 exc.errors() 整个塞进 f-string"这种写法一旦出现，覆盖不到的类型就会漏。
    """
    from app import main as main_module

    text = Path(main_module.__file__).read_text(encoding="utf-8")
    start = text.index("_handle_validation_error")
    rest = text[start:]
    handler = rest[: rest.index("@app.exception_handler", 5)]
    assert "build_validation_message" in handler, "校验处理器没有改走新的文案构造器"
    assert not re.search(r"exc\.errors\(\)[^\n]*\{", handler), "校验处理器又把整份 errors 格式化进文案"
