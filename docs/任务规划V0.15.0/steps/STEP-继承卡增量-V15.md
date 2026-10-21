# 继承卡增量（V0.15.0，2026-10-19 17:55 重建于 main@d1db090）

权威卡面仍在 `docs/任务规划V0.13.0/steps/` 与 `docs/任务规划V0.14.0/steps/`（D-V11-07）。本文件只写增量；行号以执行时现读为准。

## STEP-15b +3
| L3 | 内容 | 判据 | owner |
|---|---|---|---|
| S15b.V15.1 | （P-34 / D-V12-09）vitest 全局 setup 把 `fetch`（及 `XMLHttpRequest` 若存在）换成"调用即抛并带调用栈"的桩；各 spec 需要网络时显式 `vi.stubGlobal` 声明 | 先红：任一 spec 调一次未桩 fetch ⇒ 红并点名文件；r043 spec 在 CI-Windows 连续 3 个 head_sha 绿；禁止 `retry` | 规划方 |
| S15b.V15.2 | （P-21 + D-V12-12）`/bots` 页按 `/me` 的秩隐藏 operator 无权的入口：「新建渠道」「删除渠道」按钮，编辑弹窗里的 webhook / 密钥 / 扩展配置三个输入框（operator 只读显示"仅管理员可改"） | vitest：operator 渲染时三处不可见/只读；admin 可见；后端仍是最终门（矩阵已锁），前端只做体验 | 规划方 |
| S15b.V15.3 | （STEP-25 收尾）渠道编辑只发改动的凭据字段 | **已交付**于 7504ef8（`tests/w4-bots-tasks.spec.ts` 新增 2 条，改前红改后绿）；本项只记账 | — |

## STEP-10 +2（D-V12-13，2026-10-19 用户裁决）
| L3 | 内容 | 判据 | owner |
|---|---|---|---|
| S10.V15.1 | 把 `ArticleDetailFallbackCoordinator` 接进入库链路（`job_worker` → `kb.ingest_url` 免费直抓失败之后），开关 `article_detail_fallback_enabled` **默认 False**；**免费直抓永远先跑**；"配了付费 key"≠"启用兜底" | 先红：AST/调用图证明 Coordinator 现在全仓 0 处实例化（规划方 8cd0e68 前已读）；改后：开关关 ⇒ 付费 provider 0 次调用（mock 计数）；开关开且免费成功 ⇒ 0 次；开关开且免费失败 ⇒ 恰 1 次且受预算护栏约束 | 执行 Agent-API |
| S10.V15.2 | 触发条件与供应商做成可配置：`system_settings["article_fallback"] = {enabled, trigger: ["http_error","empty_body","captcha"], providers: ["dajiala",...], daily_budget}`，只配"何时触发 / 用哪家 / 预算"，**不配 key** | 依赖 STEP-28 的 `system_settings`；接口 operator 可读、**admin 可写**（涉及花钱，按 D-V12-12 的危险操作同族处理，规划方解释，登记 D-V12-20）；无库值 = 关 | 执行 Agent-API |
依赖更新：10 依赖 20 ✅ 与 **28**（S10.V15.2 需要 `system_settings`）；S10.V15.1 可先做。

## STEP-07 +3（D-V12-14：先在测试库演练，生产以后跑）
| L3 | 内容 | 判据 | owner |
|---|---|---|---|
| S07.V15.1 | 审计脚本只读化 + 测试库演练：脚本只发 `SELECT`，连接串由参数传入，拒绝非只读角色（`SHOW transaction_read_only` 或 `SET TRANSACTION READ ONLY` 后执行）；先在 PG16@5547 `bothot_test` 播种已知坏数据演练 | 演练读数入 EVD：每条 SQL 期望值 = 播种数；**生产读数一律写"未测"，不得写 0** | 执行 Agent-Data |
| S07.V15.2 | 加 2 条审计 SQL：① `push_tasks.created_by` 孤儿行（STEP-24 S24.3.1，LEFT JOIN users 为空）；② `bot_channels.extra_config` 明文行（**P-39**：`extra_config LIKE '{%' AND extra_config <> '{}'`） | 同上，演练值 = 播种数 | 执行 Agent-Data |
| S07.V15.3 | P-39 存量修复脚本（不执行于生产）：复用迁移 ab1005w5b 的加密逻辑把明文行重加密，dry-run 默认、`--apply` 才写 | 测试库演练：明文行数 N → 0，解密回读与原文逐字一致 | 执行 Agent-Data |

## STEP-14b +1（D-V12-12）
| L3 | 内容 | 判据 | owner |
|---|---|---|---|
| S14b.V15.1 | 管理后台"采集配置"页：渠道启用/默认、分类增删改排序与关键词；只调 STEP-28 的接口；凭据只显示"已配置/未配置"，不显示值 | vitest + 真后端联调读数；UX 四态（加载/空/错误/成功）；依赖 28 | 规划方 |

## STEP-27 +1（P-40 / D-V12-21 熔断后移交）
| L3 | 内容 | 判据 | owner |
|---|---|---|---|
| S27.V15.1 | 敏感形门**源码模式**重做（规划方两轮自修被独立复查判 FAIL 并撤回，6b3a58f）。目标：源码里的表达式不再误报，同时不比改前少报 | ① 不报（3 条用例，形状用文字描述，写测试时用字符串拼接以免门扫到自己）：键名 secret 等于解密函数调用；对象里键名 secret 冒号表单属性；键名 token 等于 settings 属性。并且 `apps/api/app/api/v1/bots.py`、`apps/web/app/bots/page.tsx`、`apps/api/app/providers/discovery/registry.py`、`apps/api/app/services/push_scheduler.py`、`scripts/entry.py` 全文 0 命中。② 照报（全部写成反证用例）：双引号字符串里的 libpq 连接串（含口令段）、字符串里的"大写键名等于值"环境行、井号注释与双斜杠注释里的赋值、反引号模板、纯数字口令、**三引号或反引号跨行字符串里的赋值**、**表达式后跟写死字面量**（取环境变量带默认值、字典 get 带默认值、`??`、`\|\|`、`or`、三元、字符串拼接；字面量≥8 字符且非占位、非全大写环境变量名）。完整构造见 `docs/任务规划V0.15.0/07-执行过程记录.md` 步 22/24 与两轮复查原文（规划方保存）。③ 全仓自有源码（不含 `.project/`）新旧门命中集合对照入 EVD：新门只能**少报表达式**，不能少报任何含字面量的行。④ 文档面（code=False）与十条具名规则、`SECRET_ALLOW`/`SECRET_ASSIGN`/`SECRET_FAKE` 字节不变。⑤ opus 独立复核 1 轮 + 变异 5/5 | Agent-Guard |
- **顺序硬约束**：S27.V15.1（连同 S27.3）必须是执行队列的**第一项**。撤回后严格口径下现读 14 个自有源码文件有 HIGH（`bots.py` 2、`registry.py` 4、`push_scheduler.py` 1、`scripts/entry.py` 2、`bots/page.tsx` 3 等），任何卡触碰这些文件都会被门挡住，且门没有豁免通道。
- S27.3（D-V12-05 扩到全部文件 + `_TOKEN` 词界）与 S27.V15.1 同批做；P-41 的召回缺口一并评估、单独登记结论。
- 可参考但**不得照搬**的历史实现：`git show c41a57d -- scripts/guards.py`（已知漏多行字符串与兜底值两类）。

## 状态更新（不增项）
- **24 ✅、25 ✅**：交付 7504ef8 + 434d56f（契约产物）+ 392a635（docstring/EVD 更正）；独立复查两轮，24/25 本体全部 PASS；门禁修复（P-40）两轮 FAIL 已撤回（6b3a58f），移交 27。
- 00P：✅。00T：余原 9 项。00R：余原 9 项。00H：仍余 S00H.2.3。
- 26：前置 25 已满足 ⇒ 可开工。21：前置 22 ✅、25 ✅ ⇒ 可开工（规划方）。
- **28 ✅（后端面，2026-10-21）**：S28.1.1 = `7c4bda8`（+ P-60 门禁修复 `9d112f7`，三绿）；S28.1.2～S28.4.2 = `05ff3ff` + 第 2 轮 `2ab19c2`（三绿，`head_sha` 核对一致）。**卡面 §2 的契约步没有合法实现路径 ⇒ 交回规划方（P-61）**，读写面与接口全部落地；页面仍属 14b。读数 `docs/06_validation/evidence/EVD-V15-28/`。
- **10 增量两行 ✅（2026-10-21）**：S10.V15.1 = `1e5c462`；S10.V15.2 = `066ceeb`（第 1 轮 `b60e1e9` 的 ubuntu 红归因见 EVD §7：`SKIP_BASELINE_WIN` 的可复查锚被新增注释挤出 1600 字符窗口，本机全量跑在改 yml 之前 ⇒ 那 6 条 skip 门用例没见过新块）。**卡面点名的 `captcha` 触发值在本仓 0 检测面 ⇒ 接口拒收并登记 P-64**；`daily_budget` 是进程内按业务日的尝试上限，跨进程持久计数仍是 S10.2.1/2（缺迁移号且依赖 STEP-08）。读数 `docs/06_validation/evidence/EVD-V17-10/s10_v15_2_readings.md`。
