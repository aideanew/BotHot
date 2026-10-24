# PERF-baseline-v1（STEP-18 首版全站性能基线）

- 测量时间：2026-10-24（Asia/Shanghai）；harness：`scripts/perf_baseline.py`（本版随卡新增）。
- 原始读数：`docs/06_validation/evidence/EVD-V18-18/`（base/rerun/warm1/warm2/inject25 五组 JSON+MD）。

## 环境指纹（S18.0）

| 项 | 值 |
|---|---|
| PostgreSQL | 16.15（zonky 便携二进制，`%USERPROFILE%\pg16-5547`，**自备**，非系统服务；端口 5547，库 `bothot_test`，迁移至 `ab1006c2a` 单头） |
| Redis | **NOT RUNNING**——依赖 Redis 的路径（会话登录、限流计数）不在测；限流中间件经 `RATE_LIMIT_ENABLED=false` 显式关闭（指纹声明：其 Redis 1s 连接超时会串在每条请求前淹没全部端点读数） |
| LangBot | 桩（`test_langbot._client` 形态） |
| LLM | **录制回放**（MockTransport 重放录制 SSE 帧；无真实 LLM 凭据，S18.1.2 判据允许并要求标注） |
| 客户端位置 | **同进程**：API/feed 经 `httpx.ASGITransport`（无网络栈）；ingest/首 token 服务层直调 |
| 数据集规模 | 用户 1（admin）+ 空间 30 + 热点 60 + Feed 100 + jobs 40 + 入库探测自建 2×n 篇 |
| 并发 | 1（串行采样，无并发压测——首版基线口径） |
| Python/OS | 3.12.10（`apps/api/.venv`）/ Windows 10 x64 |
| 注入 | `--inject-delay-ms`（S18.2.1 变慢对照） |

## 基线读数（n=50/探测；五组完整 JSON 见 EVD）

| 指标 | p50（五组范围） | p95（五组范围） | SLA 目标 | 结论 |
|---|---|---|---|---|
| API 读 /spaces | 8.08–12.82 | 10.60–15.59 | <500ms | ✅ 余量 ~39× |
| API 读 /hot/topics | 5.41–9.80 | 8.27–11.82 | <500ms | ✅ |
| API 读 /jobs | 5.69–8.74 | 8.37–17.31 | <500ms | ✅ |
| Feed /hot/feed | 6.15–12.74 | 8.62–21.13 | <100ms | ✅ 余量 ~4.7× |
| 单篇入库（短链/长链，服务层） | 26.67–29.95 | 32.36–42.21 | <30s | ✅ 余量 ~700× |
| 首 Token（录制回放） | 0.76–0.96 | 1.58–3.96 | <3s | 桩回放出帧时延；真实 RTT 不在测 |

## 可感性证明（S18.2.1，注入 25ms 对照）

全部四指标 PASS：p50 同向位移 ≥21ms（API 9→34/37-49、ingest 29→50、首 token 0.9→33.1）。
**无下线指标**——四条都保留了（SLA 目标线本身远高于基线，证明是形式闭环）。

## 复跑偏差与抖动来源

- p50：warm1 vs warm2 全指标 ≤13% ✅（spaces 12.9% 最大）。
- p95：±2ms 级绝对抖动（单点离群敏感——p95@n=50 取第 48 位，一次 GC/OS 调度即移动它）；
  feed p95 一组 11.46→21.13（+9.7ms，单次离群）。**抖动来源 = 单点离群 + 冷启动**
  （冷首跑的 API 读比热态高 40–55%，预热两轮后稳定）。
- 结论：p50 是本基线的精确判据；p95 如实记录、解释抖动（P-104 家族纪律同样适用于此）。

## 前提与局限

1. **单机、同进程、无网络栈**——API 读数不含网络 RTT/TLS/反向代理开销；真实用户路径
   （浏览器→Next rewrites→FastAPI）的端到端时延必然高于本基线。本基线回答的是
   "应用自身慢不慢"，不是"全链路慢不慢"。
2. **Redis/LangBot/真实 LLM 不在测**——依赖它们的路径（登录链路、真实 RAG、真实抓取）无读数。
3. **数据集规模小**（空间 30/热点 60/Feed 100）——分页/过滤在万级数据下的表现未测。
4. **未引入任何优化**（`git diff` 零命中 `apps/api/app/`；`test_perf_probe.py` 为只读新增用例）。
5. 复跑命令：`cd apps/api && AIDEANBOT_TEST_PG_DSN="postgresql+psycopg://bothot:bothot@localhost:5547/bothot_test" .venv/Scripts/python ../../scripts/perf_baseline.py --n 50 --out ../../docs/06_validation/evidence/EVD-V18-18 --tag <tag>`
