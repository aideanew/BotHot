---
id: PLAN-V0.2.0
title: BotHot 剩余任务规划 V0.2.0 —— 数据采集核心链路修复与测试闭环
status: proposed
baseline: main@61739f047e7a4b7fce3a89d72a4e01c1d4d77558 (2026-10-12 15:28:33 +0800)
previous: docs/任务规划V0.1.0（main@60e5723 基线，25 卡 + G-5…G-24）
created: 2026-10-12
---

# BotHot 剩余任务规划 V0.2.0

## 一句话结论

V0.1.0 的执行把力气主要花在**守卫与文档**（gitleaks、docs 门禁、漂移修正、证据包），这些交付是真的、CI 也绿；
但**数据采集这条核心业务链路存在 4 个已用探针实证的 P0 缺陷**，现有 1008 条通过的测试与全部门禁都没有拦住它们：

| # | 缺陷 | 后果 | 实证 |
|---|---|---|---|
| P0-1 | 长链 `article_key` 坍缩为 `"s"` | 同一公众号第 2 篇及以后的长链文章**被第 1 篇缓存冒名顶替**，永远不抓取 | 探针 P-3：`fetch_count=1, B.hitCache=True, same_doc=True` |
| P0-2 | Manifest 键（workUuid）≠ Asset 键（article_key） | 已入库篇被 Diff 反复判为"新增"，Job 终态后**每轮重复入列全量历史**，空轮询退避永不生效 | 探针 P-2：`已 READY 入库后 Diff 仍判为新增篇数 = 1` |
| P0-1b | 长链入库时 `_biz_from_url` 读 `biz` 不读 `__biz`，兜底走 `Source.url LIKE '%s%'` | 库内 ≥2 个信息源时**任何长链入库直接 500**（MultipleResultsFound）；单源时错挂到唯一源 | 探针 P-4：`PROBE2 EXC MultipleResultsFound` |
| P0-3 | 4 家付费源的清单行**没有 id 字段** | `_map_row` 全部返回 None ⇒ 切到 dajiala/justoneapi/tikhub/wellbyte 任一渠道时**发现产出恒为 0**（只计 skipped） | 探针 P-1：`dajiala -> None / justoneapi -> None` |

另有 P1 结构性缺口：全局单一默认渠道 + `Source.external_id` 只存 biz，而 4 家付费源要 ghid / 文章 URL、RSS 要 feed URL（标识体系不匹配）；
RSS 2.0 `pubDate` 解析恒为 None；RSS 外链被 `ALLOWED_HOSTS={"mp.weixin.qq.com"}` 拒收；详情兜底协调器生产**零调用方**（覆盖率 0%）；
4 家付费源客户端覆盖率 16%–22%、无一条测试。

因此 V0.2.0 的主轴是：**先修正确性（P0）→ 再补标识体系与渠道路由（P1）→ 再接兜底与成本护栏 → 全程以"先红后绿"的回归测试驱动**；
V0.1.0 遗留项只保留**安全与数据可见性**两类（TASK-001 轮换、G-21 广播泄露），其余治理元任务降级合并。

## 文件地图（每个步骤一个 md）

| 文件 | 内容 |
|---|---|
| `00-README.md` | 本页：结论、文件地图、执行纪律、如何复现证据 |
| `01-现状与进度基线.md` | 上一步（V0.1.0）完成度真值表、本轮实测的测试/门禁基线 |
| `02-数据采集链路穿透分析.md` | 发现→清单→Diff→Job→Worker→入库→兜底 全链路执行逻辑 + 缺陷证据链 D-01…D-16 |
| `03-需求拆解与辩证分析.md` | 需求 vs 实现逐条对账；每个关键决策的正反论证与裁决项 |
| `04-剩余任务大纲.md` | **总纲**：≥3 级、带序号、最小原子化的剩余任务体系 + DAG + 所有权矩阵 |
| `steps/STEP-00-测试环境与基线.md` | 隔离 PG/Redis、全量测试可复现、环境敏感用例修正 |
| `steps/STEP-01-文章幂等键修复.md` | P0-1：canonical article key + 存量数据审计/回填 |
| `steps/STEP-02-清单与资产键对齐.md` | P0-2：Manifest↔Asset 键对齐 + 清单状态机 |
| `steps/STEP-03-渠道行契约归一.md` | P0-3：provider 行契约、RSS 时间解析、契约测试 |
| `steps/STEP-04-信息源标识体系与渠道路由.md` | P1：biz/ghid/url/feed 多标识 + 按源路由 + 渠道降级链 |
| `steps/STEP-05-RSS一等信息源.md` | P1（条件）：RSS 作为独立 Source 类型；外链入库策略 |
| `steps/STEP-06-详情兜底接线与成本护栏.md` | P1：兜底协调器接入入库链 + 日预算/计量 |
| `steps/STEP-07-采集可观测性.md` | P2：渠道级指标、全 skip 告警、就绪度增强 |
| `steps/STEP-08-采集性能.md` | P2：清单批量 upsert、Diff 查询计划、索引 |
| `steps/STEP-09-端到端测试闭环.md` | 发现→入库 E2E（MockTransport）、修掉掩盖缺陷的测试写法、覆盖率门 |
| `steps/STEP-10-V0.1.0遗留收口.md` | TASK-001、G-21、G-19/TASK-017、待裁决项的取舍 |
| `steps/STEP-11-文档对账与发布.md` | AGENTS/README/REQ 中关于采集的不实陈述更正、EVD、版本 |
| `evidence/` | 4 个探针脚本（P-1 行映射 / P-2 重复入列 / P-3 长链冒名 / P-4 多源崩溃）+ 本轮全量 pytest 原始输出 |

## 执行纪律（对所有 STEP 生效）

1. **先红后绿**：每个修复类原子任务必须先提交一个在当前 HEAD 上**失败**的回归测试（反证），再提交修复使其通过。验收命令在"什么都没做"时必须 rc≠0（承 V0.1.0 G-17）。
2. **未列出即禁止**：每个 STEP 的"允许修改"之外一律禁止（承 G-20 建议的默认语义）。
3. **测试库隔离**：任何连库测试必须显式设置 `AIDEANBOT_TEST_PG_DSN` 指向隔离库（本规划用宿主 `5547`），**禁止**落到 `tests/conftest.py:36` 的默认 DSN（指向 5433 生产形态库）。
4. **行号会漂移**：本规划的 `file:line` 以基线 `61739f0` 为准，执行时以**符号锚**（函数/常量名）为主，行号仅辅助；每条证据都附可重算命令。
5. **数据迁移先审计后改写**：涉及存量数据（STEP-01/02）先在只读副本上跑审计 SQL，结果入 EVD，再决定回填方案。
6. **付费渠道零活体**：本规划所有验证用 `httpx.MockTransport` 录制样本；活体调用只在 STEP-04/06 的"人工验收"段由人执行，并记成本。

## 如何复现本规划的证据

```bash
# 0) 基线
git rev-parse HEAD   # 期望 61739f047e7a4b7fce3a89d72a4e01c1d4d77558（之后的提交可能使行号漂移）
# 1) 隔离 PG（任意方式起一个 16.x，端口 5547；本轮用 conda-forge postgresql=16）
export DSN="postgresql+psycopg://<user>:<pass>@127.0.0.1:5547/bothot_test"
cd apps/api && uv sync --frozen --all-extras
DATABASE_URL=$DSN .venv/bin/python -m alembic upgrade head
DATABASE_URL=$DSN AIDEANBOT_TEST_PG_DSN=$DSN .venv/bin/python -m pytest tests -q -rs --cov=app
# 2) 四个探针
.venv/bin/python ../../<plan>/evidence/probe_row_mapping.py
AIDEANBOT_TEST_PG_DSN=$DSN .venv/bin/python ../../<plan>/evidence/probe_reenqueue_loop.py
# probe_longlink_collision.py / probe_multisource_crash.py 用法见文件头（复制进 tests/ 跑完即删）
```

## 局限（诚实边界）

- 未调用任何付费上游；4 家付费源的真实响应形状以代码内注释 + registry 的 `verified_scope` 为准，未二次活体确认。
- 未接触生产库；P0-1 对存量数据的污染程度**未知**，STEP-01 第一项就是审计。
- RedFox `workUrl` 的真实形态（长链 or 短链）决定 P0-1 对订阅主路径的影响面：仓库内 R8 文档样例为长链（`.docs/03_solution/solutions/r8-…-20260928.md:226`），测试样例为短链（`tests/test_redfox_client.py:53`），二者冲突 ⇒ 列为 BLOCKING 未知项 U-01，STEP-01 用一次活体样本或生产库抽样关闭。
- 前端未做浏览器级验证；LangBot、Redis、OIDC 未起（对应 5 条 skip）。
