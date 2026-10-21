# STEP-28 采集渠道与采集分类运营可配置（后端 + 契约；页面并入 14b）

| 字段 | 值 |
|---|---|
| 1 执行者 | 执行 Agent-API |
| 2 验收者（与执行者分离） | 独立验证 Agent，只看 diff + 运行结果，只输出 PASS / FAIL / UNKNOWN |
| 3 难度 / 里程碑 | 中高 / M1 |
| 4 所属切片 | SL-COLLECT「运营在后台改采集配置 → 下一轮调度按新配置跑」 |
| 5 来源需求 | **D-V12-12**（2026-10-19 用户裁决：运营可配置采集渠道、采集分类）、REQ-F-008（管理后台） |
| 6 来源证据（main@d1db090 现读） | 渠道：`app/core/config.py:177-180` `discovery_channels`/`discovery_default_channel` 只能靠环境变量，`app/providers/discovery/registry.py:257/283-290` 只读 settings；只读接口 `GET /api/v1/admin/discovery/channels`（`admin.py:467`，operator）。分类：`app/services/categorizer.py:12` `CATEGORIES` 与 `_RULES` 写死在代码，`spaces.py:43` `CATEGORY_ALLOWLIST` 由它派生；全仓**没有**任何写接口 |
| 7 建议档位 | sonnet；升级条件：需要改冻结契约 `docs/任务规划V0.12.0/contracts/**` ⇒ 停，交规划方 |
| 8 预估规模 | 大，9 项，约 2.3 人日 |
| 9 迁移号 | **ab1006c4a**（08 持 c2a、09 持 c3a；本卡与 08/09 **禁止并行**，down_revision 以合入时 `alembic heads` 为准，单头） |

## 0. 目标（一句话，可验证）
operator 通过 `PUT` 接口改"启用哪些发现渠道 / 默认渠道"和"分类清单 + 每类关键词"，落库后**下一轮** `scheduler` 与入库分类按新配置执行；凭据（API key）不进库、不经接口、不回显；库里没配置时行为与今天逐字一致（环境变量兜底）。

## 1. 5W1H + 辩证（压缩）
- **What**：今天改渠道要改 env 重启，改分类要改代码发版；运营做不了。
- **为什么不把 key 也做成可配**：D-V12-12 只放开"渠道"和"分类"；渠道凭据属 D-V12-12 的"凭据只给管理员"同族，且 D-V12-13 未来供应商可配也只配"用哪家"，不配 key。⇒ key 仍只在部署环境变量/保险库。
- **反方案（否决）**：直接写 `.env` 文件——多进程（backend/scheduler/worker）不同步、无审计、容器内不可写。
- **反方案（否决）**：每进程启动时读一次库——改完要重启，等于没做。⇒ 采用"每轮调度/每次分类时读，带短 TTL 缓存（≤60s）"。
- **分类改名的历史数据**：`content_assets.category` 已存旧名。本卡**不回写历史**；接口禁止删除仍被引用的分类（返回 `request_invalid` 并给出引用数），只允许新增、改关键词、调顺序、停用。停用 = 不再新分进来，筛选里仍可见。

## 2. 输入
- 契约：`packages/contracts/src/**` 新增 `admin/discoveryConfig`、`admin/categoryConfig` DTO（新增，不改既有）；先写契约再写实现。
- 前置任务：STEP-25 ✅（单参数角色门 + 运营写权口径）；与 08/09 串行（迁移）。
- 前置状态：main@d1db090 或之后。

## 3. 原子任务（WP → Atomic Task → Execution Step）

### S28.1 存储
- [x] **S28.1.1** 迁移 ab1006c4a：新表 `system_settings(key varchar(64) PK, value jsonb NOT NULL, updated_by varchar(36) NULL FK users.id, updated_at timestamptz NOT NULL)`；只建表，不播种（无行 = 走 env 兜底）⇒ ✅ `7c4bda8`，形状与不变量的理由在 ADR-0013
  - S28.1.1.a 迁移往返：`alembic upgrade head && alembic downgrade -1 && alembic upgrade head` 真库 rc=0，读数入 EVD ⇒ ✅ `EVD-V15-28/s28_1_readings.md` §1（含"低点表必须真的不在"的探针，因为往返步看不见假 downgrade）
- [x] **S28.1.2** `app/services/system_settings.py`：`get(key)`（TTL≤60s 进程内缓存，Redis 可选）/ `put(key, value, actor)`（写库 + 清缓存 + 结构化审计日志：谁、何时、旧值摘要、新值摘要）⇒ ✅ 交付于 `05ff3ff`。口径差一条并留账：同步读 `peek()` **不做 IO**（签名不变的同步函数不能 await），跨进程一致靠"每轮开头刷一次"+TTL；Redis 那一层不做（配置面只有两个键，读缓存另有 `admin:discovery:channels` 那条既有路径）。审计摘要必须在赋值**之前**取，第一版把顺序写反过，被自己的用例抓到（`EVD-V15-28` §4）

### S28.2 采集渠道
- [x] **S28.2.1** `registry.py` 的 `_enabled_set`（实读函数名是 `_whitelist`） / `resolve_default_channel` 改为"库值优先、env 兜底"；签名不变 ⇒ ✅ `05ff3ff`
  - S28.2.1.a 先红：连库用例写入 `discovery={"enabled":["tikhub"],"default":"tikhub"}` 后 `resolve_default_channel` 仍返回 env 的 redfox ⇒ 红 ⇒ ✅ 红读数 `redfox`、绿读数 `tikhub`（`EVD-V15-28` §1 §3）
  - S28.2.1.b 无库值时与改前逐字一致（复用现有 registry 测试，0 修改）⇒ ✅ `test_discovery.py` 一行未改，与 `test_categorizer.py`、`test_docs_pagination.py` 同批通过
  - 补一条卡面没写但会致命的判据：库里 `enabled=[]` 是"决定全停"，env 的 `""` 是"没配=全开"，两者必须能区分（`test_empty_db_list_means_no_channel_not_every_channel`）——只改 `_whitelist` 不改它的 3 个调用点就会把"全停"执行成"全开"
- [x] **S28.2.2** `PUT /api/v1/admin/discovery/config`（`require_roles("operator")`）：只收 `enabled: list[str]`、`default: str`；校验名字必须在 `registered_channels`、`default ∈ enabled`；**拒收任何含 key/token/secret 的字段**（pydantic `extra="forbid"`）⇒ ✅；服务层 `validate()` 也 `extra="forbid"`，两道闸不合并
- [x] **S28.2.3** `GET /api/v1/admin/discovery/channels` 回显增加 `source: "db"|"env"`；写后缓存 `admin:discovery:channels` 立即失效 ⇒ ✅（失效在 commit **之后**，否则并发读会把提交前的形状再塞回缓存）

### S28.3 采集分类
- [x] **S28.3.1** `categorizer.py`：`CATEGORIES`/`_RULES` 变为默认值；`categorize()` 与 `CATEGORY_ALLOWLIST` 读 `system_settings["categories"]`（结构：`[{name, keywords[], enabled}]` 有序），无库值时与今天逐字一致 ⇒ ✅（新增 `active_categories()` / `enabled_rules()` / `category_allowlist()` / `default_categories()`）
  - S28.3.1.a 先红：库里新增分类"安全·合规"+ 关键词"漏洞" ⇒ `categorize("某漏洞通报", "")` 仍得"其他" ⇒ 红 ⇒ ✅ 本批用同形状的「质量·验收」+「验证」量到红读数 `其他`、绿读数 `质量·验收`
- [x] **S28.3.2** `GET/PUT /api/v1/admin/categories`（operator）：校验名字非空≤32 字、不重复、至少 1 个启用、`其他` 必须存在且不可停用（`DEFAULT_CATEGORY` 兜底）；删除仍被 `content_assets` 引用的分类 ⇒ `request_invalid` + 引用数 ⇒ ✅（32 字的上界不是凑数：`content_assets.category` 实测 `String(32)`）；**停用 ≠ 删除**：有引用也放行，历史行与筛选项都还在
- [x] **S28.3.3** `spaces.py` 的分类校验与呈现序跟随库值（`CATEGORY_ALLOWLIST` 改函数，调用点同步）⇒ ✅ 第 2 轮 `2ab19c2` 补完后端口径：`ensure_loaded(session)` 在三个调用点前各一行，否则"重启后的 backend 看得见配置、却按默认清单拒新分类"——一半生效比没生效更难查（判据带变异反证，`EVD-V15-28` §11）

### S28.4 权限矩阵与证据
- [x] **S28.4.1** 把新 3 个写端点加进 `tests/test_push_and_hot_rank_matrix.py` 的 `OPERATOR_OK`（user 10004 / operator·admin 非 10004）；`test_require_roles_single_arg.py` 自动覆盖 ⇒ ✅ 追加 3 行（`PUT /discovery/config`、`PUT /categories` 两个写 + `GET /categories` 一个读——卡面写"3 个新写端点"，实数是 2 写 1 读；把读也纳入矩阵，数量与覆盖面同时成立）
- [x] **S28.4.2** EVD：`docs/06_validation/evidence/EVD-V15-28/`——迁移往返、各先红原文、改后绿、端到端读数（PUT 渠道 → 调 `resolve_default_channel` 得新值；PUT 分类 → `kb.ingest` 路径分类得新值）、`@ci` 三条 run id 且 `head_sha` = 交付提交 ⇒ ✅ `s28_1_readings.md` + `s28_2_to_4_readings.md`（端到端三条都在 §3/§11；交付提交 `2ab19c2`，`head_sha` 核对见 §4 末条）

## 4. 验收标准
- [x] 迁移单头、往返 rc=0 ⇒ `ab1006c4a (head)` 单头；往返 + 低点探针读数在 `s28_1_readings.md` §1
- [x] 无库值时：现有 registry / categorizer / spaces 全部用例 0 修改通过 ⇒ `test_discovery.py`、`test_categorizer.py`、`test_docs_pagination.py` 零修改，82 passed（改后绿那一批里）
- [x] 有库值时：S28.2.1.a、S28.3.1.a 改前红、改后绿 ⇒ 红：`redfox` / `其他`；绿：`tikhub` / `质量·验收`
- [x] 接口拒收凭据字段（422），响应体不含任何 key ⇒ 拒收：`PUT` 夹带凭据形字段 ⇒ 422/10005 且库里 0 行；回显：`GET` 的响应文本里没有 `api_key`/`token`/`secret` 任一字段名。**但**框架层那一份 422 文案会回显被拒的输入值（`main.py` 取 `exc.errors()[:1]`，pydantic 恒带 `input`）——已登记 P-62，不在本卡改
- [x] 权限矩阵：3 个新写端点 user=10004、operator/admin≠10004 ⇒ 见 S28.4.1；矩阵用例整体通过
- [x] 后端全量 0 failed；ruff/mypy；CI / CI-Windows / Security 三绿；CI-Windows `SKIP_BASELINE_WIN` 按新增连库用例数抬高并在 EVD 写明算式 ⇒ 本机全量两形状：连库 `2121 tests / 0 failed / 6 skipped`、无 DSN `2121 / 0 failed / 612 skipped`；`SKIP_BASELINE_WIN` 578→612（算式 `EVD-V15-28` §8）；`ruff`/`mypy` rc=0；交付提交 `2ab19c2` 三绿：CI 39592643116 / CI-Windows 39592643124 / Security 39592643147，`head_sha` 逐条核对一致（第 1 轮 `05ff3ff` 也三绿，但它漏了后端进程那一侧，见 `EVD-V15-28` §11）

## 4b. 交回规划方的两项（本卡不做，卡面自己划的线）

1. **契约步**（卡面 §2「先在 `packages/contracts/src/**` 新增 DTO」）：三条实现路径各自是墙——`src/**` 是生成物（手改在 `--check` 逐字节比对必红）；加进 `app.contracts.collection` 会让生成物多出 `$defs`，而比对门对"稿里没有的 def"是无条件红且不查登记表；新起一个域要先有规划方落的冻结稿。⇒ 登记 **P-61**，读数与复现见 `EVD-V15-28` §6。本批的接口形状仍在 OpenAPI 里可见（三个请求模型），14b 有依据，缺的是 `packages/contracts` 那一份生成物。
2. **卡面允许面缺接线点**：§0 的目标句要求"下一轮"生效，而 §5 允许面不含 `scheduler.py` / `job_worker.py`。已按最小面（各 1 行）接上并各带行为用例，属申报过的越界，一并记在 P-61 与 `EVD-V15-28` §5。

## 5. 允许修改
- `apps/api/alembic/versions/ab1006c4a_*.py`（新建）、`apps/api/app/models/**`（仅新增 `SystemSetting`）
- `apps/api/app/services/system_settings.py`（新建）、`app/services/categorizer.py`、`app/services/spaces.py`（仅分类校验/呈现序）、`app/providers/discovery/registry.py`（仅两个读函数）
- `apps/api/app/api/v1/admin.py`（仅新增端点 + discovery 读接口加 `source`）
- `packages/contracts/src/**`（仅新增 DTO）
- `apps/api/tests/**`（新建 + 矩阵追加行）、`.github/workflows/ci-windows.yml`（仅 skip 基线数字与注释）
- `docs/06_validation/evidence/EVD-V15-28/**`

## 6. 禁止修改
- `apps/web/**`（页面属 14b，由规划方做）
- `docs/任务规划V0.12.0/contracts/**`、`app/services/roles.py`、`app/api/deps.py`
- 任何凭据读取路径（`config.py` 里的 key 字段、`secrets/`）

## 7. 依赖与阻塞
- Depends on：25 ✅；与 08、09 串行（迁移号）
- Blocks：14b 的"采集配置"页面
- 阻塞条件：发现某处在 import 期就把 `CATEGORIES` 固化成常量且无法改成函数（例如被冻结契约枚举引用）⇒ 停，登记 P-xx 交规划方

## 8. 熔断
同一判据连续 2 次验收 FAIL ⇒ 停止改代码，并排两次读数，交规划方（D-14，rounds-check 机器执行）。
