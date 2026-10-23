"""STEP-40：日志出口不落凭据（P-113 出站 URL / P-112 入站路径与 query）。

先红读数（f86811e…9c66add 上无本改动）：同一条 httpx 出站请求，日志里整行
``HTTP Request: GET https://…?token=<值>``，值原样在文本里。

判据全部用**运行时随机**的凭据形值，断言它不出现在 handler 输出的任何一行里；
同时断言主机名仍在（遮蔽不能把排障信息一起抹掉）。
"""

from __future__ import annotations

import asyncio
import io
import logging
import secrets
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import structlog

from app.core import logging as app_logging
from app.core.audit import PATH_PARAM_PLACEHOLDER, _safe_path_params
from app.core.log_redaction import QUERY_PLACEHOLDER, SEGMENT_PLACEHOLDER, redact_text
from app.providers.push.base import PushMessage
from app.providers.push.dingtalk import DingtalkPushProvider
from app.providers.push.feishu import FeishuPushProvider
from app.providers.push.wechat_work import WechatWorkPushProvider


def _secret() -> str:
    return "s40" + secrets.token_hex(12)


@pytest.fixture(params=["console", "json"])
def log_buffer(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Iterator[io.StringIO]:
    """临时把日志出口换到内存，用完把全局装配**原样**还回去。

    必须还回同一个 processors 列表对象：``capture_logs`` 是就地改当前列表，
    早先已缓存的 logger 绑的是旧列表对象；换成新列表（configure / reset_defaults
    都会换）会让它们对后续用例的 ``capture_logs`` 失明（P-63 同族，本卡首轮实测
    让 test_manifest_asset_alignment 在全量里红过一次）。
    """
    saved_config = structlog.get_config()
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    saved_flag = app_logging._configured

    buf = io.StringIO()
    monkeypatch.setenv("LOG_FORMAT", request.param)
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setattr(app_logging, "_resolve_stream", lambda: buf)
    app_logging.configure_logging(force=True)
    try:
        yield buf
    finally:
        monkeypatch.undo()
        for h in list(root.handlers):
            root.removeHandler(h)
        for h in saved_handlers:
            root.addHandler(h)
        root.setLevel(saved_level)
        structlog.configure(**saved_config)
        app_logging._configured = saved_flag


def _ok_transport(body: dict[str, Any]) -> httpx.MockTransport:
    return httpx.MockTransport(lambda _req: httpx.Response(200, json=body))


def _patch_client(monkeypatch: pytest.MonkeyPatch, module: Any, body: dict[str, Any]) -> None:
    real = httpx.AsyncClient

    def factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = _ok_transport(body)
        return real(*args, **kwargs)

    monkeypatch.setattr(module.httpx, "AsyncClient", factory)


# ── 真推送 provider：凭据在 URL 里的三家 ─────────────────────────────────────


def test_dingtalk_access_token_and_sign_not_logged(log_buffer: io.StringIO, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.providers.push import dingtalk

    token, sign_secret = _secret(), _secret()
    _patch_client(monkeypatch, dingtalk, {"errcode": 0, "errmsg": "ok"})
    msg = PushMessage(
        message="m",
        webhook_url=f"https://oapi.dingtalk.com/robot/send?access_token={token}",
        secret=sign_secret,
    )
    result = asyncio.run(DingtalkPushProvider().push(msg))
    assert result.delivered
    out = log_buffer.getvalue()
    assert "HTTP Request" in out, "前提：httpx 这一行确实被打出来了，否则断言是空转"
    assert token not in out
    assert "oapi.dingtalk.com" in out


def test_wechat_work_key_not_logged(log_buffer: io.StringIO, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.providers.push import wechat_work

    key = _secret()
    _patch_client(monkeypatch, wechat_work, {"errcode": 0, "errmsg": "ok"})
    msg = PushMessage(message="m", webhook_url=f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key}")
    asyncio.run(WechatWorkPushProvider().push(msg))
    out = log_buffer.getvalue()
    assert "HTTP Request" in out
    assert key not in out
    assert "qyapi.weixin.qq.com" in out


def test_feishu_hook_path_token_not_logged(log_buffer: io.StringIO, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.providers.push import feishu

    hook = _secret()
    _patch_client(monkeypatch, feishu, {"code": 0, "msg": "success", "StatusCode": 0})
    msg = PushMessage(message="m", webhook_url=f"https://open.feishu.cn/open-apis/bot/v2/hook/{hook}")
    asyncio.run(FeishuPushProvider().push(msg))
    out = log_buffer.getvalue()
    assert "HTTP Request" in out
    assert hook not in out
    assert "open.feishu.cn/open-apis/bot/v2/hook/" in out


# ── 错误路径：HTTPStatusError 的 str 自带完整 URL，provider 用 %s 带出 ──────────


def test_http_status_error_url_in_warning_is_redacted(log_buffer: io.StringIO) -> None:
    token = _secret()
    req = httpx.Request("GET", f"https://api.justoneapi.com/api/x?token={token}")
    exc = httpx.HTTPStatusError("x", request=req, response=httpx.Response(401, request=req))
    exc_text = f"Client error '401 Unauthorized' for url '{req.url}'"
    structlog.get_logger("s40").warning("JustOneAPI detail 不可达: %s", exc_text)
    try:
        raise exc
    except httpx.HTTPStatusError:
        structlog.get_logger("s40").exception("带栈")
    out = log_buffer.getvalue()
    assert token not in out
    assert "api.justoneapi.com" in out


# ── 纯函数：形状表 ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("template", "kept"),
    [
        (
            "HTTP Request: POST https://oapi.dingtalk.com/robot/send?access_token={s}&timestamp=1&sign=x",
            "oapi.dingtalk.com/robot/send",
        ),
        ('"GET /api/v1/spaces?q={s} HTTP/1.1" 200', "/api/v1/spaces"),
        ('{{"event": "x", "url": "https://h.example/a/{s}/b"}}', "https://h.example/a/"),
        ("wss://push.example/ws/{s}", "wss://push.example/ws/"),
        ("for url 'https://api.example/x#{s}'", "https://api.example/x"),
    ],
)
def test_redact_text_shapes(template: str, kept: str) -> None:
    s = _secret()
    out = redact_text(template.format(s=s))
    assert s not in out
    assert kept in out


def test_redact_text_leaves_plain_text_and_short_segments() -> None:
    plain = "订阅 3 条入库，耗时 1.2s"
    assert redact_text(plain) is plain
    assert redact_text("https://redfox.hk/api/v1/work/list") == "https://redfox.hk/api/v1/work/list"
    assert QUERY_PLACEHOLDER in redact_text("https://h.example/a?x=1")
    assert SEGMENT_PLACEHOLDER in redact_text("https://h.example/hook/abcdefghijklmnop")


# ── 审计：路径参数的值 ────────────────────────────────────────────────────────


def test_audit_path_params_keep_uuid_and_short_ident_mask_the_rest() -> None:
    uid = "0b7c3f5e-1d2a-4c8b-9e6f-0a1b2c3d4e5f"
    s = _secret()
    got = _safe_path_params({"space_id": uid, "engine": "redfox", "doc_id": s, "x": "a b"})
    assert got == {
        "space_id": uid,
        "engine": "redfox",
        "doc_id": PATH_PARAM_PLACEHOLDER,
        "x": PATH_PARAM_PLACEHOLDER,
    }


# ── STEP-43：异常栈（P-114 栈帧局部变量 / P-115 JSON 无栈） ─────────────────────


def _raise_with_local(secret_value: str) -> None:
    raise RuntimeError("s43-boom")


def test_exception_keeps_stack_and_never_shows_frame_locals(log_buffer: io.StringIO) -> None:
    s = _secret()
    try:
        _raise_with_local(s)
    except RuntimeError:
        structlog.get_logger("s43").exception("原生日志带栈")
        logging.getLogger("s43.third").exception("第三方日志带栈")
    out = log_buffer.getvalue()
    assert out.count("s43-boom") >= 2, "两条日志都必须带出异常（P-115：JSON 模式此前只剩 exc_info=true）"
    assert "_raise_with_local" in out, "必须有栈帧，不只是异常消息"
    assert s not in out, "栈帧局部变量不得进日志（P-114）"


def test_console_renderer_pins_plain_traceback(monkeypatch: pytest.MonkeyPatch) -> None:
    """rich 是否可导入取决于开发机；渲染器必须显式固定 plain_traceback，不吃缺省值。"""
    saved_config = structlog.get_config()
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    saved_flag = app_logging._configured
    monkeypatch.setenv("LOG_FORMAT", "console")
    monkeypatch.setattr(app_logging, "_resolve_stream", io.StringIO)
    app_logging.configure_logging(force=True)
    try:
        ours = [h for h in root.handlers if getattr(h, app_logging._OUR_HANDLER_ATTR, False)]
        assert len(ours) == 1
        fmt = ours[0].formatter
        assert isinstance(fmt, structlog.stdlib.ProcessorFormatter)
        consoles = [p for p in fmt.processors if isinstance(p, structlog.dev.ConsoleRenderer)]
        assert len(consoles) == 1
        assert consoles[0]._exception_formatter is structlog.dev.plain_traceback
    finally:
        monkeypatch.undo()
        for h in list(root.handlers):
            root.removeHandler(h)
        for h in saved_handlers:
            root.addHandler(h)
        root.setLevel(saved_level)
        structlog.configure(**saved_config)
        app_logging._configured = saved_flag
