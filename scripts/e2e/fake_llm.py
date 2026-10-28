#!/usr/bin/env python
"""假 LLM 上游（OpenAI 兼容 chat/completions，SSE 流式）——STEP-72 S72.1。

只用标准库：`http.server` + `ThreadingHTTPServer`，零第三方 import。

协议依据（产品侧只读，不解释成"与真实厂商一致"）：
- 请求：`POST /v1/chat/completions`，body `{"model","messages","stream":true}`，
  头 `Authorization: Bearer <key>`（`apps/api/app/api/v1/chat.py:240-248`）。
- 响应按行读，只认 `data: ` 前缀，`[DONE]` 结束，chunk 取 `choices[0].delta.content`
  （`chat.py:281-288`）。首 token 必须 < `LLM_FIRST_TOKEN_TIMEOUT`=15s（`chat.py:268`），
  否则产品侧判 `50002`；故首个 `data: ` 帧**立即**发，不等任何东西。
- `/v1/embeddings`、`/v1/rerank` 回 404：启动器把 `EMBEDDING_API_BASE` 也指到本服务，
  而 `reranker.py:99-101` 对上游 >=400 降级为"保序回退"（不新增错误码）。

模式（`?mode=` 优先，其次环境变量 `FAKE_LLM_MODE`，默认 `normal`）：
- `normal` —— 首帧立即，随后每 50ms 一段，共 3 段，然后 `[DONE]`；
- `slow`   —— 首帧延迟 16s（跨过 15s 锚点，逼出「响应较慢」的 degraded 分支）；
- `abort`  —— 发 1 段后直接关连接（不发 `[DONE]`），逼出流中断的 error 分支。

用法：`python scripts/e2e/fake_llm.py --port 3290`
"""

import argparse
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

FIRST_TOKEN_DELAY_SLOW = 16.0  # > LLM_FIRST_TOKEN_TIMEOUT(15s)，见 chat.py:268
CHUNK_INTERVAL = 0.05

# 固定正文：读数可复算，不随请求变化
SEGMENTS = (
    "假 LLM 首段：这是来自本机假上游的固定回复。",
    "第二段：仅用于验证 SSE 帧能被逐行解析、增量渲染不丢字。",
    "第三段：生成结束。",
)


def _mode_from(path: str) -> str:
    query = parse_qs(urlparse(path).query)
    mode = (query.get("mode") or [os.environ.get("FAKE_LLM_MODE", "")])[0]
    mode = (mode or "normal").strip().lower()
    return mode if mode in ("normal", "slow", "abort") else "normal"


def _chunk(text: str) -> bytes:
    payload = {"choices": [{"delta": {"content": text}}]}
    return ("data: " + json.dumps(payload, ensure_ascii=False) + "\n\n").encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "fake-llm/1"

    def log_message(self, fmt: str, *args: object) -> None:  # 落 fake_llm.out，供证据直贴
        sys.stderr.write("fake_llm: " + fmt % args + "\n")
        sys.stderr.flush()

    def _send_json(self, status: int, body: dict) -> None:
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self) -> None:  # noqa: N802  （http.server 的固定方法名）
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)  # 读掉 body：不读会让 keep-alive 收到半截请求
        if path == "/v1/chat/completions":
            self._stream(_mode_from(self.path))
            return
        if path in ("/v1/embeddings", "/v1/rerank"):
            # 404 是给 reranker 的安全降级信号（reranker.py:99-101），不是"没实现"
            self._send_json(404, {"error": {"message": f"fake upstream: {path} 未提供", "code": 404}})
            return
        self._send_json(404, {"error": {"message": f"fake upstream: 未知路径 {path}", "code": 404}})

    def _stream(self, mode: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Fake-Mode", mode)
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True  # 不声明长度 ⇒ 以连接关闭结束正文

        if mode == "slow":
            time.sleep(FIRST_TOKEN_DELAY_SLOW)

        self.wfile.write(_chunk(SEGMENTS[0]))
        self.wfile.flush()
        if mode == "abort":
            return  # 1 段后直接关：不发 [DONE]，产品侧应走流中断分支

        for text in SEGMENTS[1:]:
            time.sleep(CHUNK_INTERVAL)
            self.wfile.write(_chunk(text))
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def do_GET(self) -> None:  # noqa: N802
        self._send_json(404, {"error": {"message": "fake upstream: 只提供 POST /v1/chat/completions", "code": 404}})


def main() -> int:
    parser = argparse.ArgumentParser(description="假 LLM 上游（SSE 流式）")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3290)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.daemon_threads = True
    mode_default = os.environ.get("FAKE_LLM_MODE") or "normal"
    print(f"fake_llm 监听 http://{args.host}:{args.port}（mode 默认 {mode_default}）", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
