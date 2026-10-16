# BotHot 剩余任务规划 V0.12.0（基线 main@3a67e96）

> 项目：AideanBotHot｜仓库 `https://github.com/aideanew/BotHot` 分支 main｜端口段 3200-3300（前端 3200 / 后端 3300）
> 规划日期：2026-10-15｜上一版 V0.11.0（第二增量基线 17c5d28）｜本版是它的增量：30 张卡随件继承（编号不复用、不重排），新增 1 张。
> 开工前 `git fetch` + `git merge --ff-only`；先验入站文件与在途脏文件 0 交集再快进。

## 0. 一句话结论

**主干看上去已经"双绿"，其实不是：Security 最近两次 success，但 CI 工作流最近 10 次结论全部是 `cancelled`。** ubuntu 五个 job 每次都绿，唯独 `windows-dev` 的全量 pytest 每次跑满 35 分钟被超时取消，整个工作流的结论就跟着变成 cancelled。任何只看工作流结论的人都会读成"CI 没跑完"，而不是"Ubuntu 绿、Windows 断"。（证据 `evidence/3a67e96/workflow_runs_main.json`、`ci_run_38707720244_jobs.json`）

**卡死的根因已基本定位，而且它同时是一个生产缺陷。** `app/main.py:281` 在 import 期执行 `app = create_app()`，后者在 `_assert_schema_current` 里同步 `asyncio.run()` 连库探测，而探测引擎（`app/db.py:53-59`）没有 `connect_timeout`。Linux 上本地拒连会立即返回，所以 CI ubuntu 不受影响；Windows 对拒连要约 2 秒，再加上 psycopg 只在 Selector 事件循环下才真正发起连接（conftest.py:26 正好设了它），于是 pytest 一 import 到 `app.main` 就变得极慢甚至挂住。我在 Linux 上把 `DATABASE_URL` 指向一个黑洞地址，`import app.main` 直接挂满 25 秒（rc=124）：**生产机只要启动时数据库所在网络丢包而不是拒连，uvicorn 就会在 import 期无限挂起。**（证据 `evidence/3a67e96/win_stall_rootcause_probe.txt`）

**因此本版只新增一张 P0 卡 STEP-00W**：给启动探测加超时、把 windows-dev 拆成独立工作流（让 CI 结论只反映正式验收面）、在 Windows job 加逐用例超时与 faulthandler 取栈，用 @win 栈闭合根因。其余 30 张卡继承，状态按 3a67e96 的真实代码与读数刷新。

**本版核实后的进度**：@linux 连库全量 **1058 passed / 5 skipped / 0 failed，覆盖率 79%，77.36 秒**；Security 回绿（00S 完成）；管理端运维四屏已上线（14b 大部分完成）；Win10 工具链与入口跨平台化完成一半（00X）。**采集域主线（01→02→04→07，P-1/P-2/P-3）仍一行没动**，这是剩余工作中真正的核心。

## 1. 本版相对 V0.11.0 的变化

| # | 变化 | 证据 |
|---|---|---|
| 1 | 基线 17c5d28 → **3a67e96**，其间 13 个提交：00X（entry.py/guards.py/windows-dev job）、00S（Security 回绿）、15 S15.2.3（admin-ops typed 客户端）、14b（`/admin/ops` 四屏） | `git log 17c5d28..3a67e96` |
| 2 | **CI 工作流最近 10 次全部 `cancelled`**；同一批 run 中 ubuntu 五个 job（backend / frontend / compose / compose-smoke / workflow-lint）全部 success，windows-dev 在「Backend tests」步被取消 | evidence/3a67e96/*.json |
| 3 | **U-20 根因定位**：import 期同步连库探测无超时；@linux 黑洞地址复现挂死；与 @win 读数（拒连 2.05s、alembic 挂 150s、裸 import 快、pytest 采集慢）逐条吻合 | win_stall_rootcause_probe.txt |
| 4 | 新增 **STEP-00W**（8 个三级任务 / 1.0 人日 / opus / 规划方执行） | steps/STEP-00W-*.md |
| 5 | 新增裁决 **D-V7-01～D-V7-03**（按用户授权代选，见 03 §1） | 03 |
| 6 | 纠正历史口径「管理端 6 组接口无前端消费」：push、ops/liveness、discovery/channels、engines/keys **4 组已被 `lib/api/admin-ops.ts` 消费**；backchannel-logout 是 IdP→本服务的服务间回调，**按设计不需要前端**；`admin/alerts` **后端并无此路由**（告警状态只在 `/system` 就绪聚合里以 `alerting: enabled/disabled` 出现） | 01 F-07 |
| 7 | @linux 读数首次与 CI ubuntu 对齐：1058/5/0、79%、收集 1063 条 1.23s（@win 同一收集 262.65s） | pytest_linux_3a67e96.txt |
| 8 | 规模：**31 卡 / 200 三级任务 / 30.75 人日**（继承 30 卡 192/29.75 + 00W 8/1.0）；剩余数逐卡见 04 §2 | 04 §2.1 复算脚本 |

## 2. 阅读顺序
1. `01-事实基线与进度.md`：快照 + 已确认事实 + 文档与代码不一致清单
2. `02-需求拆解与辩证分析.md`：需求复核、5W1H、钢人论证
3. `03-裁决与契约.md`：新裁决 + 六份契约（`contracts/`，唯一源规则不变）
4. `04-剩余可执行大纲体系.md`：31 卡总表、DAG、所有权矩阵、档位与预算
5. `steps/STEP-00W-*.md`：本版唯一新卡；其余卡为 V0.11.0 随件继承，**卡内"执行记录"截至 17c5d28 之后的 13 个提交**，状态以 04 §2 为准
6. `05-风险自检与局限.md`、`06-入库与双端一致.md`、`07-执行过程记录.md`

## 3. 规划方（本 Agent）与执行 Agent 分工
- **规划方自执行（核心 + 高难度 + UI）**：00W（P0 根因）、01（采集域契约冻结）、13（引擎能力面）、14a（管理端后端聚合）、14b 余项（通用表 S14b.2.1、告警横幅 S14b.2.3）、15 余项。
- **执行 Agent（中等/简单）**：00X 余项、00E、RV、00T、00R、17、02、03、04、05、06、07、08、09、10、11、12、18、19、00G/00P 余项。
- 判定一律由独立验证者看 diff + 运行结果，只出 PASS / FAIL / UNKNOWN（继承 V0.11.0 07 §4 的规则）。

## 4. 执行段新查出的可立即认领小条目（发布给执行 Agent，不排队）

都是我在 00W / 01 执行期间**现读**发现的，属于中等或简单，规划方不自执行（分工见 §3）。
每条给"现读锚"和"出门判据"，认领者不必再定位。

| # | 条目 | 现读锚 | 出门判据（机器） | 归属卡 |
|---|---|---|---|---|
| P-1 | `conventions.md` 仍写"CI 的 `windows-dev` job 会跑它"——`windows-dev` 自 D-V7-01 已拆到 `CI-Windows` 工作流 | `docs/04_engineering/conventions.md:119` | 该行不再出现 `windows-dev`；且新文本里的 job/步名与 `.github/workflows/ci-windows.yml` 的 step 名逐字一致 | 00X 余项（该文件不在 00W 允许清单，我改了又自行还原） |
| P-2 | `glossary.md` 三处代码锚漂移 | `docs/00_governance/glossary.md:46` 引 `kb.py:554-557` 实际在 `apps/api/app/services/kb.py:587`（`def _article_key`）；同条引 `entities.py:99` 实际字段在 `:108`（`external_id`）；`:51-53`（幂等键 / 收件人可见性 / 过期回退）由**前一会话**已补入，本会话只确认了行在、**未复核其锚** | 每条锚指向的行含被引用的符号名（脚本逐条 grep 即可） | 01 S1.4.2（属简单核对，随 17 或 01 余项皆可） |
| P-3 | **缺 ADR 链接存在性机械门**：`adr-index.md` 引用不存在的 ADR 文件时不会变红——0008/0009/0010 断链五版无人知，因为 `check_docs_consistency` 只校验 backlog 的路径与行号 | `scripts/guards.py`（守卫唯一源）、`docs/03_solution/decisions/adr-index.md` | 新增守卫：索引里每个 `](adr-NNNN-*.md)` 与每个 `**status:**` 值可对文件校验；故意删一个 ADR 文件 ⇒ 守卫必须红 | 00G（熔断/台账门）或 00P（机械门） |
| P-4 | `.gitleaksignore` 第 57–60 行三条豁免**在本克隆内永不生效**（`798f2638…` 对象不存在；无前缀路径不在可达历史里），而不可生效的豁免不会让门禁红 ⇒ 没人会被绊 | `.gitleaksignore:55-60`；事实链见 `docs/任务规划V0.12.0/08-…md` §9.5 与 U-21 | 用 CI 的真实 `gitleaks.json` artifact 重导豁免集（D-V4-04 禁止猜指纹），并加一条"死豁免检测"：每条指纹的 commit 必须 `git cat-file -t` 可达 | 00S 余项 |
| P-5 | **U-23**：`CI-Windows` 五个读数都在 ~20 分钟被 `--timeout=300` 打断（failure 非 cancelled，D-V7-02 生效）。栈指向**同步 `TestClient` 等 anyio blocking portal**，与 psycopg/启动探测无关 | `docs/06_validation/evidence/EVD-V7-00W/ciwin_e7e9f25_timeout_stack.txt`；`readings_ci_close.md` §3 | 先 `-v` 拿用例名，再 `--timeout=60 -k` 二分定位到单个用例/fixture；`CI-Windows` 结论变 success 或给出"该用例在 Windows 上结构性不可用"的裁决 | 新卡或 00R（测试域） |
| P-6 | `pytest-timeout` 在 `pyproject.toml` dev extra 里，但**未进 `uv.lock`**（U-19 同族） | `apps/api/pyproject.toml` dev 段 | `uv lock` 后 `uv.lock` 含 `pytest-timeout==2.4.0` 且 `uv sync` + 全量 pytest 不回归 | U-19 / 00S S0S.3 |
| P-7 | **`scripts/*.py` 不在任何 lint 面里**：CI 只跑 `ruff check app tests`（`ci.yml:68`），而 ruff 配置住在 `apps/api/pyproject.toml` ⇒ 从仓库根跑 `scripts/` 吃不到 `line-length=120`，从 `apps/api` 跑才吃到——S1.3.1 的 `E501` 就是这么漏过去又被抓回来的 | `.github/workflows/ci.yml:68`；`docs/06_validation/evidence/EVD-V2-01/s131_gen_contracts.md` §7.1 | 新增一步（或把 `scripts` 加进现有 ruff 目标）并保证**固定 cwd**；反证：故意在 `scripts/` 里写一行 121 字符 ⇒ 门禁必须红 | 00P 余项（机械门）或 00X 余项 |
| P-8 | **本机 `core.autocrlf=true` 与 `.gitattributes eol=lf` 打架**：6 个 `packages/contracts/src/**/dto.ts` 在 worktree 里是 CRLF 而仓库 blob 是 LF；`git status` 报 ` M` 但 `git diff` 为空 ⇒ 提交前必须逐次辨别"eol 伪差异" | `docs/06_validation/evidence/EVD-V2-01/s131_gen_contracts.md` §7.3 全表 | 要么 `git add` 后确认 blob 哈希未变、要么在文档里给出"如何辨别 eol 伪差异"的两条命令。**注意：不允许 AI 改 git config**，所以处置只能是文档化 + 选择性暂存 | 00X 余项（跨平台口径） |
| P-9 | **事件快照静默置空串无人可见**：`_hydrate_payload` 查不到对象时把模板变量置 `""` 并**继续发事件**，于是推送文案可能出现空标题而任何指标都不动。契约冻结稿已把这条记为已知缺陷并写"转 STEP-05"，但 **STEP-05 卡面现在没有这一项**（`grep -n "payload\|空" STEP-05-*.md` 无命中，本次现读） | `apps/api/app/services/push_events.py:29-66`（置空点 `:31`、`:45-46`）；`docs/任务规划V0.12.0/contracts/events.schema.json#/definitions/EventPayloadRules` 的 `x-known-defect`；`docs/任务规划V0.12.0/steps/STEP-05-采集静默告警与可观测.md` | 每个被置空的快照字段产一个计数（命名与本卡指标族一致，如 `bothot_event_payload_empty_total{name,field}`）+ 一条 structlog 告警；并有一条用例证明"对象查不到 ⇒ 计数 +1 且日志可见"，而不是只断言"事件照样发出去了"。语义**不改**（仍置空仍发事件），只把不可见变成可见 | 05（采集静默告警与可观测） |

| P-10 | **同一个 `sub` 在两域有两种形状**：identity 域有 `Sub`（1..64，DB 列 `users.sub String(64) UNIQUE`），而 resources 域稿面的 `InAppNotification.sub` 是裸 `string`。收编时**没有**替它套 `Sub`——那等于给这份合同加它没声明的边界；但让两域各自表述也不是解决 | `docs/任务规划V0.12.0/contracts/resources.schema.json` 的 `definitions.InAppNotification`；`apps/api/app/contracts/resources.py` 的 `sub-not-aliased-to-identity` 登记；`apps/api/app/contracts/identity.py` 的 `Sub` | 一次裁决后两域产物对 `sub` 给出同一形状（要么都带 1..64，要么稿面明写不设界）；改完 `test_inapp_notification_sub_is_deliberately_unbounded` 必须红或按新形状更新，不许留绿 | 01 余项（S1.2.2 第五域 `api` 收编时一并判最省） |
| P-11 | **IDOR 连库矩阵未落地**：S1.4.3 的两层静态面已交付（枚举完整性 + "身份不许被丢掉"的 AST 底线，本机 `@win` 可跑，并据此抓到、修好了两条真洞——见 `EVD-V2-01/s143_idor_floor.md`），但**逐端点的 A-vs-B 请求**要播种两个用户 + 空间 + 文档 + 作业，必须连 PG；本机 5432/5433 现读拒连，且 31 条全 skip 的"绿"是 U-20 明令禁止的形状，所以没塞进 CI | 端点清单**已生成**在 `apps/api/tests/test_idor_matrix.py`（`CHECKLIST_OPERATIONS`，31 条：9 条 `/api/v1/admin/**` 走角色门、22 条走属主门；期望码取自 `contracts/identity.schema.json#/x-idor-checklist`）；播种助手锚 `tests/test_r11_admin_routes.py:48-105`、`tests/test_r04_jobs.py:48-78`；`db_session` 的 skip 判据 `tests/conftest.py:100-128` | 31 条参数化用例在 `@ci` ubuntu 全绿：每条要么 403/10004 或 404/30004，要么入参层先拒**且** B 的行逐字未变；再加 S1.4.3.3 的反证——临时摘掉任一属主校验 ⇒ 至少一条必须红，全绿说明矩阵没接上真路由 | 01 S1.4.3（余项） |
| P-12 | **稿面清单比路由表窄**：`x-idor-checklist` 只点名 `space_id/job_id/doc_id`，而路由表另有 16 个带 `channel_id`(5) / `source_id`(3) / `task_id`(3) / `subscription_id`(1) / `topic_id`(1) 的操作同样按 id 定位资源、却没有属主规则——`engine`(2) 与 `report_date`(1) 不是属主键，留在规则外 | 现读枚举见 `apps/api/tests/test_idor_matrix.py` 的 `UNLISTED_OPERATIONS`（守卫 `test_owner_ids_outside_the_frozen_checklist_are_visible` 钉住 16 这个数）；规则文本在 `docs/任务规划V0.12.0/contracts/identity.schema.json#/x-idor-checklist` | 一次裁决：要么把这几类 id 写进 `x-idor-checklist`（则 P-11 的矩阵随之变长，守卫会红着要求更新数字），要么在稿面显式声明"这些 id 不属主"并给出理由。**不许**由实现者顺手在枚举里加参数名——那是替合同加面 | 01 余项 / 规划方裁决 |
