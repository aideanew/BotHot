# BotHot 剩余任务规划 V0.13.0（基线 main@314d7f2）

> 项目：AideanBotHot｜仓库 `https://github.com/aideanew/BotHot` 分支 main｜端口段 3200-3300（前端 3200 / 后端 3300）
> 规划日期：2026-10-17（Asia/Shanghai）｜上一版 V0.12.0（基线 3a67e96，执行记录续写至 314d7f2）｜本版是它的增量：31 张卡随件继承（编号不复用、不重排），新增 6 张，重开 1 张。
> 开工前 `git fetch` + `git merge --ff-only`；本版规划开始时本地 HEAD 落后 6 个提交（b8d27ff→314d7f2，全部是 STEP-04 S4.2），已快进，`rev-list --left-right --count HEAD...origin/main = 0 0`。

## 0. 一句话结论

**主干的"绿"遮住了两个真实缺陷，两个都不是测试能自然抓到的形态。**

1. **安全：任何已登录的普通用户都能读出全部推送渠道的明文凭据**——这直接抵消了 REQ-NF-002「渠道密钥 AES-256-GCM 加密落库」：库里加密，接口解密后发给所有人。 `GET /api/v1/bots` 与 `GET /api/v1/bots/{id}` 只有登录门、没有角色门，响应里回显 webhook 令牌和**解密后**的 `extra_config`（飞书 `app_secret`、钉钉 `access_token`）。我在真库上用一个无角色用户复现了：两个接口都 200，两样都漏；对照组 PUT 有角色门，401。（`evidence/314d7f2/probe_bots_read_by_plain_user.txt`）→ **STEP-22（P0）**
2. **功能：推送任务列表接口永远 404。** `/{channel_id}` 声明在 `/tasks` 之前，`GET /api/v1/bots/tasks` 被当成"查 id 为 tasks 的渠道"。前端正在调它；后端 1478 条用例没有一条打这个路径；前端默认走手写 mock，所以页面看起来正常。（`evidence/314d7f2/route_shadow_bots_tasks.txt`）→ **STEP-22 + STEP-15b**

**CI-Windows 自拆出以来一直红（314d7f2 之前最近 5 次全部 failure，`evidence/314d7f2/workflow_runs_main.json`），本版把根因怀疑面换了回来。** V0.12.0 结论是"卡在 TestClient/anyio portal，与 psycopg 无关"。我逐条对过：被卡的三条用例**只做一件事——`GET /system/health`**；`/health` 串行等三个探针，redis 2s、langbot 3s 都有上界，**唯独 PG 探针用业务引擎、没有 `connect_timeout`**；Windows 回环不回 RST（执行方自己的读数），CI-Windows 又没有 PG ⇒ 每次 `/health` 都是一次无上界的黑洞连接。`@linux` 黑洞 DSN 下 `/health` 在 314d7f2 上挂满 45s。portal 线程停在 `selectors._select` 正是"路由协程在等 connect"的样子。→ **STEP-00H（P0）**，`部分确认`：机制已证，"Windows 上就是它"待 `@ci` 读数。

**进度**：`@linux` 真库全量 **1478 passed / 5 skipped / 0 failed，覆盖率 85%，108.7s**（V0.12.0 基线是 1058 / 79%）；`CI`、`Security` 在 314d7f2 均 success；02、03 已交付；04 的形状层（迁移 `ab1006c1a`）已交付，**行为层（Diff 与四态）一行未动**——采集主线真正的剩余核心仍在 04→05/06→07。

## 1. 本版相对 V0.12.0 的变化

| # | 变化 | 证据 |
|---|---|---|
| 1 | 基线 3a67e96 → **314d7f2**；V0.12.0 期间执行方交付 00W、00S、02、03、04-S4.2、14b 四屏、15-S15.2.3 等 | `git log 3a67e96..314d7f2`；V0.12.0 `04` 状态列 |
| 2 | **新增 STEP-22（P0 安全）**：推送域 4 个读接口补角色门 + `/tasks` 路由前置 + 两道防复发守卫 | probe_bots_read_by_plain_user.txt、route_shadow_bots_tasks.txt |
| 3 | **新增 STEP-00H（P0）**：健康/就绪探针加上界并改并发；判别 H2/H3；CI-Windows 回绿 | probe_health_blackhole.txt（b8d27ff 与 314d7f2 两次）、ciwin_38937542471_stall_excerpt.txt |
| 4 | **新增 STEP-20**：发布清单 P-15/16/17（付费源时间 naive、TikHub 4xx/5xx 抛异常、WellByte `null` 打挂整页）转为正式卡 | V0.12.0 `00-README` §4；本版逐行复核锚点 |
| 5 | **新增 STEP-21**：发布清单 P-11/P-12（IDOR 连库矩阵 + 清单扩面）转为正式卡；`@linux` 现在有 PG，前提已具备 | `tests/test_idor_matrix.py` docstring |
| 6 | **新增 STEP-15b**：前端 mock 默认值翻转 + mock 由契约生成（STEP-15 执行记录明说"属独立一张卡"） | `apps/web/lib/api/http.ts:18-19` |
| 7 | **重开 STEP-02（新增 S2.4）**：规范键不规范化 `mid/idx` 前导零 ⇒ 同文两键 | probe_leading_zero.txt |
| 8 | 新裁决 **D-V10-01～D-V10-08**；签入两条拖了一天的 BLOCKING：**D-V8-05、D-V8-08 取 A**（用户 2026-10-15 授权规划方代选） | `03` §1；`docs/03_solution/decisions/decision-log.md` |
| 9 | **新增 STEP-23**：REQ-F-001 自己登记、五天无人认领的缺口——手动/测试直投不写站内通知历史（`persist_web_notification` 全仓仍只有 1 个调用点） | `product-requirements.md:66-74`；`push_scheduler.py:229` |
| 10 | `make evidence-check` 在 314d7f2 红（证据脚本 AST 抽函数陈旧，非生产缺陷），作为 STEP-00T 首个迁移对象 | `evidence/314d7f2/evidence_check.txt` |
| 11 | 规模：**37 卡 / 235 三级任务 / 38.25 人日**；**剩余 166 项 ≈ 27.5 人日**（继承剩余 131 项 ≈20.0 + 新增 35 项 7.5） | `04` §2 |

## 2. 阅读顺序
0. `06-入库与双端一致.md` 的文件清单即本版落盘清单
1. `01-事实基线与进度.md`：快照、已确认事实、文档与代码不一致清单
2. `02-需求拆解与辩证分析.md`：需求复核、5W1H、三轮追问与钢人论证
3. `03-裁决与契约.md`：本版裁决 + 六份契约（冻结稿仍在 `docs/任务规划V0.12.0/contracts/`，本版不复制，见 D-V10-06）+ 数据模型与迁移序
4. `04-剩余可执行大纲体系.md`：36 卡总表、四级大纲、切片、DAG、并行判定、所有权矩阵、档位与预算、指标
5. `steps/STEP-00H|20|21|22|23|15b-*.md` 为本版新卡；`STEP-02` 末尾追加 S2.4；其余卡随件继承，状态以 `04` §2 为准
6. `05-风险自检与局限.md`、`06-入库与双端一致.md`、`07-执行过程记录.md`

## 3. 分工
- **规划方自执行（核心 + 高难度 + UI）**：**00H、22**（P0，立即）→ 21（安全）→ 15b（前端核心）→ 01 余项（D-V8-05/08 已签，可动）→ 13、14a、14b 余项、15 余项。
- **执行 Agent（中等/简单）**：04 行为层、20、02-S2.4、23（22 之后）、00X 余项、00E、RV、00G、00P、00T、00R、17、05、06、07、08、09、10、11、18、19、12。
- 判定由独立验证者看 diff + 运行结果，只出 PASS / FAIL / UNKNOWN（规则继承 V0.11.0 `07` §4）。
