#!/usr/bin/env python
"""假 LangBot（登录 + 知识库检索两个路由）——STEP-72 S72.2。

只用标准库：`http.server` + `ThreadingHTTPServer`，零第三方 import。

协议依据（产品侧只读，不解释成"与真实 LangBot 一致"）：
- 登录：`POST /api/v1/user/auth`，body `{"user","password"}`，token 取 `data.token`
  或顶层 `token`（`apps/api/app/providers/langbot/client.py:52-68`、`_extract_token` `:217-225`）。
- 检索：`POST /api/v1/knowledge/bases/{kb_uuid}/retrieve`，
  body `{"query","retrieval_settings":{"top_k","search_type"}}`，结果取 `data.results`
  （`client.py:198-211`）。
- 成功信封必须带 `code: 0`：`client.py:102-103` 判 `code not in (None, 0)` 即业务错误。
- 结果条目的形状**逐字复用** `apps/api/tests/test_chat_sse.py:49-62` 的 `_results()`：
  `{"content": [{"text", "file_name"}], "score"}`——`content` 是**列表**，不加
  `distance` 等测试里没有的字段（`_context_texts` 两者都吃得下，但只有这一形有测试背书）。
- `file_name` **必须**是 `fake-doc-1`：`chat.py:83-96` 的 `_filter_by_allowed` 只保留
  file_name 落在候选集合里的条目，而候选集合来自 STEP-73 种子的 `langbot_file_id`。

鉴权：检索与引擎清单都要求带本进程签发的那一个 Bearer 值，不对就回 401。这是本卡刻意选的更严口径
（**不是**对真实 LangBot 鉴权行为的断言——真上游怎么校验登录，本服务不模拟、也无从证明），
作用是让"产品没登录就直接检索"这类缺陷在这里就红，而不是被假服务掩盖。

用法：`python scripts/e2e/fake_langbot.py --port 3291`
"""

import argparse
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# 令牌占位取模板形（尖括号）是刻意的：CI 的敏感形门（`scripts/guards.py` 的 SECRET_ASSIGN）把
# 「键名 + 等号 + 引号字面量」判成口令赋值形，而它自己列的"占位不算秘密"形状里就有模板形 ⇒
# 这样写不触发门，也不用往 `.gitleaksignore` 登记指纹（那一面归 STEP-00S，不在本卡）。
TOKEN = "<fake-token>"
FILE_NAME = "fake-doc-1"
TEXT = "假 LangBot 检索到的固定正文：这是用于验证问答链路的占位内容，不来自任何真实知识库。"
SCORE = 0.92

_RETRIEVE_RE = re.compile(r"^/api/v1/knowledge/bases/[^/]+/retrieve$")


def _ok(data: object) -> dict:
    return {"code": 0, "msg": "success", "data": data}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "fake-langbot/1"

    def log_message(self, fmt: str, *args: object) -> None:  # 落 fake_langbot.out，供证据直贴
        sys.stderr.write("fake_langbot: " + fmt % args + "\n")
        sys.stderr.flush()

    def _send_json(self, status: int, body: dict) -> None:
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _authorized(self) -> bool:
        return (self.headers.get("Authorization") or "").strip() == "Bearer " + TOKEN

    def do_POST(self) -> None:  # noqa: N802  （http.server 的固定方法名）
        path = self.path.split("?", 1)[0]
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        if path == "/api/v1/user/auth":
            # 不校验用户名口令：本服务是上游替身，凭据口径归产品侧配置
            self._send_json(200, _ok({"token": TOKEN}))
            return
        if _RETRIEVE_RE.match(path):
            if not self._authorized():
                self._send_json(401, {"code": 401, "msg": "未登录", "data": None})
                return
            self._send_json(200, _ok({"results": [
                {"content": [{"text": TEXT, "file_name": FILE_NAME}], "score": SCORE},
            ]}))
            return
        self._send_json(404, {"code": 404, "msg": f"未知路径 {path}", "data": None})

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/api/v1/knowledge/engines":
            # 产品侧 `/system/health` 的 langbot 探针打的就是这条（`system.py:124`（探测行 `:138`））：
            # 它要求「响应 401 且 body 是带 code 的信封」才算 ok。不提供这条路由时，
            # 本服务只会回 404 ⇒ 探针读数变成 `unhealthy`（不是 `unreachable`，但也不是「被认出来」）。
            if not self._authorized():
                self._send_json(401, {"code": 401, "msg": "未登录", "data": None})
                return
            self._send_json(200, _ok([]))
            return
        self._send_json(404, {"code": 404, "msg": "fake langbot 只提供 POST 登录/检索与 GET 引擎清单", "data": None})


def main() -> int:
    parser = argparse.ArgumentParser(description="假 LangBot（登录 + 检索）")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3291)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.daemon_threads = True
    print(f"fake_langbot 监听 http://{args.host}:{args.port}（file_name={FILE_NAME}）", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
