"""测试出站地址常量（STEP-00R S0R.2.1）。

仓库内测试的「必然无人应答」HTTP 目标只允许取自本模块。禁止再写「9999 端口恰好空闲」
这类假设——只要任何人（或某个开发机上恰好起着的服务）占用该端口并返回 2xx，测试就会
以完全不同的形态失败，且失败原因看起来像业务缺陷。

`REFUSED_HTTP_URL` 用端口 1：<1024 在 POSIX 上需要 root 才能监听，Windows 也把 1
保留给 TCP port-multiplexer 服务，故「本机有 HTTP 服务监听其上」在实际开发环境不成立
⇒ connect 立即被拒。拒连（而非状态码）才是 provider 侧 `retryable=True` 的确定性来源。

配合 `tests/conftest.py` 的 `_isolate_proxy_env` autouse 夹具使用：只换地址而不清代理，
宿主代理仍会把请求接走并回一个真实的 HTTP 状态码。
"""

from __future__ import annotations

REFUSED_HTTP_URL = "http://127.0.0.1:1/bothot-hook-no-listener"
