# STEP-40 日志出口凭据遮蔽

> 基线 main@9c66add｜状态：🟡 规划方已交付代码，待 @ci 三绿与独立复查｜版本 V0.19.0

| 字段 | 内容 |
|---|---|
| 1 归属 | **规划方**（核心安全，D-V19-01） |
| 2 验收者 | 执行助手做独立复查（只看 diff + 运行结果，输出 PASS / FAIL / UNKNOWN） |
| 3 难度 / 里程碑 | 高 / M4 |
| 4 来源 | P-113（本版新登记）、P-112①②；D-V19-01～03 |
| 5 目标 | 任何经本进程日志出口的行里，不出现出站 URL 的 query、令牌形路径段，也不出现调用方塞进路径参数的任意文本 |
| 6 输入 | `app/core/logging.py`、`app/core/audit.py`、`app/providers/push/*.py`、`app/providers/article_sources/justoneapi.py` |
| 7 输出路径 | 新增 `apps/api/app/core/log_redaction.py`、`apps/api/tests/test_log_redaction.py`；改 `apps/api/app/core/logging.py`（formatter 处理器链 +1）、`apps/api/app/core/audit.py`（`_safe_path_params`）；证据 `docs/06_validation/evidence/EVD-V19-40/` |
| 8 验收标准 | 见"完成判据" |
| 10 命令 | `cd apps/api && python -m pytest -q tests/test_log_redaction.py tests/test_audit_log.py` |
| 12 允许修改 | 第 7 格所列 |
| 13 禁止修改 | 冻结契约、迁移、provider 本体（不在调用点逐个修） |
| 14 依赖 | 无 |
| 15 档位 | opus（安全审查） |
| 16 规模 | ≈0.5 人日（已完成） |

## 三级任务
1. [x] **S40.1** 先红：真推送 provider（钉钉、企业微信、飞书）走 MockTransport，随机凭据在日志里原样出现；`HTTPStatusError` 文本带完整 URL ⇒ 8 条用例在无遮蔽时红
2. [x] **S40.2** `log_redaction.py`：`redact_text()` 纯函数 + `redact_rendered()` 处理器，挂在渲染器之后
3. [x] **S40.3** 审计 `path_params`：UUID 或 ≤15 位短标识符保留，其余遮蔽
4. [x] **S40.4** 本机：ruff / mypy / 新用例 / 审计用例 / 全量回归
5. [ ] **S40.5** 推送后读 @ci 三绿（规划方回填到证据 §5）
6. [ ] **S40.6** 独立复查（执行助手在 STEP-42 开工时做，结论写进 `EVD-V19-40/s40_review.md`）

## 完成判据
- `tests/test_log_redaction.py` 15 条全绿（console、json 两种渲染各一遍）；去掉 `redact_rendered` 后其中 8 条红（反证读数在证据里）
- 后端全量 0 failed；`ruff check app tests`、`mypy app` 通过
- 同一 head 三绿

## 已知边界（不是缺陷，写明给复查者）
- 不管"把凭据当裸字符串打日志"的路（不在 URL 里）；
- 绝对 URL 里 ≥16 位的段一律遮，出站 URL 里的 UUID 资源 id 也会被遮；
- 相对路径只省 query，不遮段（入站资源 id 要留给审计）。
