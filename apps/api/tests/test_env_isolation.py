"""S0R.1.1：测试出站与宿主代理环境解耦的锁定用例（M-06 / I-01）。

为什么需要本文件（根因，非端口占用）：STEP-00 的 S0.2.1 把 webhook 投递目标从
「9999 端口上的空闲假设」改成保留拒连地址 `http://127.0.0.1:1/...` 之后，
`test_event_delivery_failure_no_reclaim` 在有环境代理的机器上**仍然失败**——
`webhook.py:33` 的 `httpx.AsyncClient` 默认 `trust_env=True`，进程环境存在 http/https
代理时，发往 127.0.0.1 的请求被代理接走并回 HTTP 404；`webhook.py:46` 只对 ≥500 判
可重试 ⇒ `retryable=False` ⇒ `retry_count` 不推进。证据：
`docs/任务规划V0.3.0/evidence/proxy_rootcause_4afaedd.txt` §C（有代理=404）/§D（清代理=拒连、
同文件 11/11 通过）。修复在 conftest 的 `_isolate_proxy_env` autouse 夹具（S0R.1.2）。

三条用例的分工（避免「永远不可能失败」的断言，G-23）：
- ① 正向对照：`NO_PROXY` 恰好等于夹具写入的那个值——宿主不会凭空有这个值，夹具没跑就红；
- ② 行为锚：拒连地址必须产出「异常型 reason」，一旦出现 HTTP 状态码即说明请求没直达目标；
- ③ 反向对照：以收集期快照为条件——宿主本来干净时它 skip（不冒充判定力），宿主脏时它是硬断言。

设计意图是「①③ 互补，使本文件在干净宿主与脏宿主两类机器上都至少有一条有判定力」。
③ 的 skip 分支与 ①② 的真实通过**尚未在本机验证**（无 venv/httpx，登记为 H-1）；
此处的静态可证部分只有：`EVD-V2-00R/prove_net_isolation.py` 的 NR-12（结构：3 条用例、
每条都有 assert、快照在用例之前）与 NR-4/NR-6（夹具行为）。
"""

from __future__ import annotations

import os

import pytest
from conftest import _PROXY_ENV_VARS, NO_PROXY_ISOLATION_VALUE
from fixtures.net import REFUSED_HTTP_URL

from app.providers.push.base import PushMessage
from app.providers.push.webhook import WebhookPushProvider

# 收集期快照：模块导入发生在任何夹具运行之前，故此处的 os.environ 就是宿主原貌。
# 只快照「夹具承诺删除」的那 6 个键——NO_PROXY/no_proxy 由夹具**覆写**而非删除，若按
# `endswith("PROXY")` 一并计入，宿主只设了 NO_PROXY（Clash/v2ray 类代理的常见形态，
# 也正是本步要对付的环境）时 ③ 必红：把一次成功的覆写判成了泄漏。
_DELETED_NAMES = {name.upper() for name in _PROXY_ENV_VARS}
_HOST_PROXY_VARS_AT_COLLECT: tuple[str, ...] = tuple(
    sorted(k for k in os.environ if k.upper() in _DELETED_NAMES)
)


async def test_proxy_env_is_cleared_for_every_case() -> None:
    """①夹具写入的正向对照 + ②代理变量已被清干净。"""
    assert os.environ["NO_PROXY"] == NO_PROXY_ISOLATION_VALUE
    assert os.environ["no_proxy"] == NO_PROXY_ISOLATION_VALUE
    leaked = [name for name in _PROXY_ENV_VARS if name in os.environ]
    assert leaked == [], f"autouse 夹具未清除代理变量：{leaked}"


async def test_refused_url_fails_as_connection_error_not_http_status() -> None:
    """行为锚：对保留拒连地址的投递必须报「连接异常」，不能报 HTTP 状态码。

    出现 `HTTP 4xx/5xx` 即等于「请求被别的东西接走了」（代理或端口占用者），那正是
    STEP-00 遗留的失败形态——本用例把它钉成不可回退。
    """
    result = await WebhookPushProvider().push(PushMessage(message="x", webhook_url=REFUSED_HTTP_URL))
    assert result.delivered is False
    reason = result.reason or ""
    assert "HTTP " not in reason, f"请求未直达目标（疑被代理接走）：reason={reason!r}"
    # 「未抵达」只有两种产出形态（webhook.py:48-51）：连接层异常，或连接超时。
    # 宿主对回环闭包端口是 DROP 而非 REJECT（EVD-V2-00R §3.7 / 事实 F-24），故不能只认「拒连」那一种；
    # 出现第三种文案说明 Provider 的失败分类变了，必须显式复核而不是让它悄悄绿。
    assert reason.startswith(("webhook 推送异常", "webhook 请求超时")), (
        f"reason 既非连接异常也非超时，Provider 失败分类已变更：reason={reason!r}"
    )
    assert result.retryable is True, (
        f"未抵达目标时应可重试（webhook.py:49 超时支、:51 异常支均置 retryable=True）："
        f"reason={reason!r}"
    )


def test_host_proxy_state_is_not_inherited() -> None:
    """③宿主原貌对照：宿主设过待清的 6 个代理变量时，夹具必须让它们对用例不可见。"""
    if not _HOST_PROXY_VARS_AT_COLLECT:
        pytest.skip("宿主未设这 6 个待清代理变量，本条对照在此环境下无判定力（①②仍有）")
    still_visible = [name for name in _HOST_PROXY_VARS_AT_COLLECT if name in os.environ]
    assert still_visible == [], f"宿主代理泄漏进用例：{still_visible}"
