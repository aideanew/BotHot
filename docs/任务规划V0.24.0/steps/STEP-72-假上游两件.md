# STEP-72：假上游两件（假 LLM + 假 LangBot）

## 1. 归属

- 所属切片：P-C 供给层
- 来源需求：`02` M-8；台账 P-149、D-V23-17
- 来源方案：D-V24-11
- 执行者：执行助手

## 2. 目标

`bash scripts/e2e/run_real_backend.sh --with-fake-llm --with-fake-langbot` 能起一套「后端 :3300 + 前端 :3200 + 假 LLM :3290 + 假 LangBot :3291」，且 `POST /api/v1/chat/ask`（带 cookie）能收到 `delta` 帧而不是 30002。

## 3. 输入

- 文档：`01` §2.5（供给侧现状）、`03` §1 的 D-V24-11
- 契约（**协议唯一依据，逐字对齐**）：
  - LLM：`chat.py:236-300`——请求 `{"model","messages","stream":true}` + `Authorization: Bearer <key>`；响应按行读，只认 `data: ` 前缀，`[DONE]` 结束，chunk 取 `choices[0].delta.content`；首 token 必须 < 15s（`LLM_FIRST_TOKEN_TIMEOUT`）
  - LangBot auth：`client.py:52-68`——`POST /api/v1/user/auth`，body `{"user","password"}`，token 取 `data.token` 或顶层 `token`（`_extract_token` `:217-225`）
  - LangBot retrieve：`client.py:198-211`——`POST /api/v1/knowledge/bases/{kb_uuid}/retrieve`，body `{"query","retrieval_settings":{"top_k","search_type"}}`，结果取 `data.results`；每项形如 `{"content":{"text","file_name"},"score","distance"}`
  - 响应必须带 `code: 0`（`client.py:97-99` 判 `code not in (None, 0)` 即业务错误）
- 前置任务：**STEP-71**（同改 `run_real_backend.sh`，71 先落地）
- 前置状态：`run_real_backend.sh:14` 已有 `--with-fake-llm`；`:254-255` 明写 `fake_llm.py` 不存在

## 4. 输出

- 新增：`scripts/e2e/fake_llm.py`
- 新增：`scripts/e2e/fake_langbot.py`
- 修改：`scripts/e2e/run_real_backend.sh`（新增 `--with-fake-langbot`、`fake_langbot` 角色端口 3291、`LANGBOT_BASE_URL` export、`stop_all` 白名单加一条）
- 新增：`docs/06_validation/evidence/EVD-V24-72/`

## 5. Execution Steps

1. [x] **S72.1** `fake_llm.py`：只用标准库（`http.server` + `ThreadingHTTPServer`），**不引新依赖**
   - `POST /v1/chat/completions`：先发 `data: {"choices":[{"delta":{"content":"<首段>"}}]}\n\n`（**立即发，不等**，避免 15s 首 token 超时），随后按 50ms 间隔再发 2–3 段，最后 `data: [DONE]\n\n`
   - 响应头 `Content-Type: text/event-stream`
   - 支持 `?mode=slow`（首 token 延迟 16s，用于 `degraded` 的「响应较慢」分支）与 `?mode=abort`（发 1 段后直接关连接，用于 `error` 的流中断分支）；用环境变量 `FAKE_LLM_MODE` 选择，**默认正常**
   - `POST /v1/embeddings` 与 `POST /v1/rerank` 回 404（`reranker.py:144-145` 会落到同基址；404 安全降级，见 `chat.py:120-123`）
2. [x] **S72.2** `fake_langbot.py`：同样只用标准库
   - `POST /api/v1/user/auth` → `{"code":0,"data":{"token":"fake-token"}}`
   - `POST /api/v1/knowledge/bases/<kb>/retrieve` → `{"code":0,"data":{"results":[{"content":{"text":"<固定正文>","file_name":"fake-doc-1"},"score":0.92,"distance":0.08}]}}`
   - `file_name` 的值**必须**是 `fake-doc-1`（与 STEP-73 种子的 `langbot_file_id` 逐字一致，否则 `chat.py:83-96` 把结果全过滤掉）
   - 其它路径回 404
   - 形状**逐字复用** `apps/api/tests/test_chat_sse.py` 的 `_results()`，不得自创字段
3. [x] **S72.3** 启动器接线：
   - `--with-fake-langbot` 解析（`:35` 一带）
   - `role_port` 加 `fake_langbot) echo 3291 ;;`（`:85` 一带）
   - 端口预检把 3291 纳入（`WITH_FAKE_LANGBOT=1` 时）
   - 启动顺序：假 LLM → 假 LangBot → 后端（**必须在 uvicorn 之前 export**，`LANGBOT_BASE_URL=http://127.0.0.1:3291`，与 `:270-271` 的 `LLM_API_BASE` 同位置）
   - `stop_all` 的命令行白名单加 `*"scripts/e2e/fake_langbot.py"*`
   - 缺文件时的报错照 `:254-255` 的形写
4. [x] **S72.4** 起栈自测（本机无 docker 也要能起，因为两件假服务都是纯 Python）：

   ```bash
   bash scripts/e2e/run_real_backend.sh --with-fake-llm --with-fake-langbot --no-frontend
   curl -s -X POST http://127.0.0.1:3291/api/v1/user/auth -H 'Content-Type: application/json' -d '{"user":"a","password":"b"}'
   curl -s -X POST http://127.0.0.1:3290/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"m","messages":[],"stream":true}'
   bash scripts/e2e/run_real_backend.sh --stop
   ```

5. [x] 本卡单独提交并推送

## 6. 验收标准

- [ ] `python -c "import ast;ast.parse(open('scripts/e2e/fake_llm.py').read())"` 通过（同理 `fake_langbot.py`）
- [ ] 两个脚本**零第三方 import**（`grep -E "^(import|from) (httpx|fastapi|uvicorn|aiohttp)"` = 0）
- [ ] `auth` 返回体含 `"token"`，`_extract_token` 能取到（`data.token`）
- [ ] `retrieve` 返回体的 `data.results[0].content.file_name` == `fake-doc-1`
- [ ] 假 LLM 的首个 `data: ` 帧在**连接后 1s 内**发出（否则 15s 锚点会误触「响应较慢」）
- [ ] `bash -n scripts/e2e/run_real_backend.sh` 通过
- [ ] `--with-fake-llm --with-fake-langbot` 起栈后 `/system/health` 的 `langbot` 不再是 `unreachable`
- [ ] `--stop` 后 3290/3291 均无监听
- [ ] `@ci` 的 `Stop stack` 仍 success（本卡改了 `stop_all` 白名单）
- [ ] 本卡不改 `apps/api/app/**` 一个字节

## 7. 验证命令

```bash
cd /d/Code/AideanBotHot
python -c "import ast;[ast.parse(open(p,encoding='utf-8').read()) for p in ['scripts/e2e/fake_llm.py','scripts/e2e/fake_langbot.py']];print('syntax ok')"
grep -nE "^(import|from) (httpx|fastapi|uvicorn|aiohttp|requests)" scripts/e2e/fake_llm.py scripts/e2e/fake_langbot.py || echo "0 第三方（期望）"
bash -n scripts/e2e/run_real_backend.sh && echo "sh syntax ok"
```

## 8. 证据路径

`docs/06_validation/evidence/EVD-V24-72/`（两脚本的 curl 响应原文 + 起栈后 health 读数 + stop 后端口读数）

## 9. 允许修改

- `scripts/e2e/fake_llm.py`（新增）
- `scripts/e2e/fake_langbot.py`（新增）
- `scripts/e2e/run_real_backend.sh`
- `docs/06_validation/evidence/EVD-V24-72/**`

## 10. 禁止修改

- `apps/api/app/**`（含 `config.py`、`chat.py`、`client.py`——**产品代码一个字节都不动**，全靠环境变量指走）
- `apps/api/tests/test_chat_sse.py`（它是形状的来源，不许改）
- `apps/web/**`、`packages/contracts/**`
- `.github/workflows/ci.yml`（CI step 归 STEP-60）

## 11. 依赖与阻塞

- Depends on：STEP-71（同文件串行）
- Blocks：STEP-73、STEP-60
- 阻塞条件：
  - 起栈后 `/system/health` 的 `langbot` 仍 `unreachable` ⇒ 先查 `LANGBOT_BASE_URL` 是否在 uvicorn **之前** export（`:270` 的位置是模板）
  - `ask` 仍返 30002 且日志显示「空间知识库未初始化」⇒ 那是 STEP-73 的种子问题，不是本卡，**不要在本卡改种子**
  - 发现需要改产品代码才能让假服务被认 ⇒ **停手**，交回规划方（说明协议面比 `01` §2.5 记的更大）

## 12. 建议执行档位

opus。理由：两个假服务的协议保真度决定 STEP-60 的全部读数；形状错了会让 60 把「自己的桩」当成「产品通过」。

## 13. 升级条件

- 需要判断「某帧该不该发」而没有代码依据（`chat.py:236-300` 没覆盖到的路径）⇒ 升级 fable
- 假服务能起但 `ask` 恒 30002 且已排除种子因素 ⇒ 升级 opus review 并交回规划方

## 14. 预估规模

中，≈0.8 人日，大于 2 小时。

## 15. 熔断

同一判据 2 轮未过 ⇒ 停手，登 P 号。

## 16. 交接物

`EVD-V24-72/` 必须含：两个 curl 的响应**原文**（不是摘要）、起栈后 health 的 `langbot` 字段、stop 后 `ss`/`netstat` 读数。**保真度不可证**这一点也要写进证据，不许写成「与真实 LangBot 一致」。
