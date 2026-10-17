# STEP-21 IDOR 连库矩阵与属主规则扩面（发布清单 P-11 / P-12，V0.13.0 新增）

| 字段 | 值 |
|---|---|
| 归属-切片 | S-M1（"A 用户看不到、改不到 B 用户的空间/文档/作业/订阅"是用户主路径的可演示安全行为） |
| 归属-需求 | 冻结契约 `docs/任务规划V0.12.0/contracts/identity.schema.json#/x-idor-checklist`（含 `{space_id}/{job_id}/{doc_id}` 的端点必须证"属主 = 当前 sub"或"rank ≥ operator"，否则 403/10004 或 404/30004；契约测试须为**每个**此类端点生成 A-vs-B 用例） |
| 归属-方案 | STEP-01 S1.4.3（静态两层已交付：`tests/test_idor_matrix.py` §1–2）；D-V10-04（本版代选：清单扩面的三类划分） |
| 里程碑 | M1 |
| 执行者 | **规划方**（安全；需要逐端点判属主语义） |
| 档位 | opus　理由：每个端点"属主是谁"是语义判断，不能模板化 |
| 规模 | 大（≈1.75 人日；7 个三级任务） |
| 依赖 | Depends on：22（推送域规则先落）、00H（`CI-Windows` 读数可比；不是硬阻塞）　Blocks：19、12 |
| 基线 | main@314d7f2 |

## 现读
- `tests/test_idor_matrix.py` 第 3 节（连库 A-vs-B）在文件 docstring 里写明"必须连 PG"，本机 `@win` 无 PG ⇒ 一直未落（P-11）。`@linux` 现在有 PG16（本目录 `07` §环境），`@ci` ubuntu 也有 ⇒ **前提已具备**。
- 稿面清单只点名 `space_id/job_id/doc_id`；路由表另有 `channel_id`(bots.py :250/:259/:296/:315/:372)、`task_id`(bots.py :508/:581/:598)、`subscription_id`(subscriptions.py :193/:226；admin.py :603)、`source_id`(subscriptions.py :99/:120；admin.py :648)、`topic_id`(hot.py :107) 同样按 id 定位资源（P-12；行号为 314d7f2 现读）。

## D-V10-04 三类划分（代选，理由逐条）
| 类 | 端点 | 规则 | 依据 |
|---|---|---|---|
| A 属主类 | `space_id/job_id/doc_id`、`spaces/{space_id}/subscriptions/{subscription_id}` | 属主 = 当前 sub，否则 404/30004（不泄露存在性） | 冻结稿原文；订阅挂在空间下，属主随空间 |
| B 运营类 | `channel_id`、`task_id`、`/sources/{source_id}`（PATCH/DELETE）、`admin/*` | rank ≥ operator（admin 路由 ≥ admin），否则 403/10004 | 这些是全局资源，无个人属主；STEP-22 已把推送域读接口拉齐 |
| C 公共只读 | `hot/topics/{topic_id}` | 登录即可读，无属主 | 热点是全站共享内容（`hot.py:45` router 级仅登录门） |

## 目标（可验证的一句话）
对 A 类每个端点生成"A 用户用 B 的 id"连库用例并全部得 404/30004 且 B 的数据未变；对 B 类每个端点生成"user 角色访问"用例并全部得 403/10004；清单由路由表枚举，新增带 id 端点而未归类会让测试红。

## 输入
- `tests/test_idor_matrix.py`（复用其路由摊平与用例 id 生成）；`docs/任务规划V0.12.0/contracts/identity.schema.json`；STEP-22 交付
## 输出（文件）
- 改：`apps/api/tests/test_idor_matrix.py`（新增第 3 节连库矩阵与第 4 节 B 类矩阵）
- 改：冻结稿 `docs/任务规划V0.12.0/contracts/identity.schema.json` 的 `x-idor-checklist`（追加三类划分；**唯一一处契约改动，由本卡持有**）。该键在唯一源 `apps/api/app/contracts/identity.py:8-11` 中被明确登记为 `x-not-in-single-source`（治理矩阵，Pydantic 无表达），执行面是 `tests/test_idor_matrix.py:253` 读的这份稿 ⇒ 改稿不改 Pydantic，`gen_contracts --check` 不受影响
- 修（仅当矩阵抓到洞）：对应 `apps/api/app/api/v1/*.py` 的单个端点
- 证据：`docs/06_validation/evidence/EVD-V13-21/`

## Execution Steps
1. [ ] **S21.1.1** 契约：在冻结稿 `x-idor-checklist` 数组追加第三条（A/B/C 三类及端点前缀，文字与本卡 D-V10-04 表逐字一致），并新增同级键 `x-idor-classes`（机器可读：`{"A": [...前缀], "B": [...], "C": [...]}`）；跑 `tests/test_collection_contract.py` 与 `gen_contracts --check` 均绿；稿 diff 入 EVD
2. [ ] **S21.1.2** 枚举守卫：所有带路径参数的路由必须落在 A/B/C 之一，未归类 ⇒ 红（替换 `test_owner_ids_outside_the_frozen_checklist_are_visible` 的"可见"为"必须归类"）
3. [ ] **S21.2.1** 播种夹具：两用户 A/B（role=user）+ 一个 operator；B 拥有空间、文档、作业、订阅各一
4. [ ] **S21.2.2** A 类连库矩阵：参数化到每个 A 类端点 × 方法；断言 404/30004，并在请求后回查 B 的行未变（写方法）
5. [ ] **S21.2.3** B 类矩阵：每个 B 类端点 × user 角色 ⇒ 403/10004；× operator ⇒ 非 403
6. [ ] **S21.3.1** 动态反证：临时把一个 A 类端点的属主过滤去掉 ⇒ 对应用例红（输出入 EVD，然后还原）
7. [ ] **S21.3.2** 若矩阵抓到真实洞：逐个修复（每洞一个提交，先红后绿），并在本目录 `07` 登记

## 验收标准
- [ ] `@linux` 与 `@ci` 上第 3/4 节用例数 = 枚举出的 A 类端点×方法数 + B 类端点×方法数（两数打印入 EVD），全部通过
- [ ] 枚举守卫反证：新增一个临时 `GET /api/v1/_probe/{foo_id}` 路由 ⇒ 守卫红
- [ ] 动态反证输出入 EVD
- [ ] `gen_contracts --check` 通过；真库全量 `failed = 0`

## 验证命令
```bash
cd apps/api && . .venv/bin/activate
AIDEANBOT_TEST_PG_DSN=postgresql+psycopg://postgres@127.0.0.1:5547/bothot_test python -m pytest tests/test_idor_matrix.py -q -rs
cd ../.. && python scripts/gen_contracts.py --check
```

## 证据路径
`docs/06_validation/evidence/EVD-V13-21/`

## 允许修改
- `apps/api/tests/test_idor_matrix.py`
- `docs/任务规划V0.12.0/contracts/identity.schema.json`（仅 `x-idor-*` 键；本卡执行期间 Contract 列由本卡独占）
- 仅当 S21.3.2 触发：被抓到的单个端点所在 `apps/api/app/api/v1/*.py`
- `docs/06_validation/evidence/EVD-V13-21/**`

## 禁止修改
- `apps/api/app/api/deps.py`、`apps/api/app/services/roles.py`
- 其他域契约（collection/events/resources/envelope）、`apps/api/app/contracts/**`、`packages/contracts/**`
- `apps/api/alembic/**`、`apps/web/**`

## 依赖与阻塞
- Depends on：22
- Blocks：19、12
- 阻塞条件：某端点属主语义无法从代码判定（例如资源无 `user_id`/`space_id` 列）⇒ 停下登记到 03 待裁决，不猜

## 建议执行档位
opus　理由：安全与契约

## 升级条件
矩阵抓到的洞需要改 `deps.py` 的共享依赖（影响全站）⇒ 升 fable

## 预估规模
大　7 个三级任务，单个 < 2h；≈1.75 人日
