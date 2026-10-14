# STEP-R0 短链缓存回归修复与合入前全量门

| 项 | 值 |
|---|---|
| 里程碑 | **M0（最高优先，第一刀）** |
| 档位 | sonnet（默认档 opus；本卡被 V0.6.0 判为 sonnet，理由是单函数改动 + 已有实测补丁。**升级条件见下**） |
| 规模 | 小（约 0.5 人日；单个三级任务均 <2h） |
| 基线 | **main@13acacc**（V0.6.0 为 a9b194d；`apps/api/app` 两者逐字节相同，见 01 F-65） |
| 依赖 | —（先于或与 STEP-00C 同 PR） |
| 被依赖 | STEP-02（规范键须在缓存链路正确的基础上改） |
| 裁决 | 无需任何裁决（01/03 一致确认） |
| 需求锚 | REQ-F-004「公众号链接入库」；MUST M-1 |
| 剩余原子任务 | **9**（V0.6.0 为 7；本版 +2：S-R0.2.4 假 docstring 修正、S-R0.1.2 判据可满足性前置检查）👤 1 |

## 归属
- 所属切片：S-M0 回归止血
- 来源需求：REQ-F-004（`docs/02_requirements/product-requirements.md:93`）
- 来源方案：V0.6.0 02 §2.0 / 本版 02 §5.1 根因链；03 §5 ADR-0011 的前置

## 目标（可验证的一句话）
短链（URL 无 `__biz`）二次入库时 `stub.fetch_count == 1 ∧ hitCache == True ∧ hitCount == 1 ∧ docId` 与首抓相同，且 P-4（多源锚定不崩）不回退。

## 输入
- 文档：`docs/任务规划V0.7.0/01-事实基线与上一步复核.md` F-65/F-72/F-73/F-74/F-75/F-76；`02` §5.1
- 契约：`contracts/resources.schema.json#/definitions/ArticleKey`（现状栏 `"s"`）、`#/definitions/ShortLinkMap.x-write-rule`
- 前置任务：无
- 前置状态：`main@13acacc` 单头迁移 `ab1005w5b`；`apps/api/app` 自 078dc30 未变

## 输出（新增/修改文件，精确到文件）
- `apps/api/app/services/kb.py`（**仅** `_find_source_by_anchor` 函数体 + 两处 docstring）
- `apps/api/tests/test_kb_multisource_anchor.py`（新增 2 条）
- `apps/api/alembic/versions/ab1006r0a_*.py`（可选，仅当数据量门槛触发）
- `docs/06_validation/evidence/EVD-V3-R0/`（读数）

## Execution Steps
1. [ ] ✅ **S-R0.1.1 锁定回归**：依赖执行机上跑哨兵命令，记录红/绿与 skip 形态
   - 命令：`cd apps/api && .venv/bin/python -m pytest tests/test_be02_engine_routing.py -q -k short_link_second -rs`
   - ⚠ **必须带 `-rs`**：本机/无 PG 环境该用例是 **skip 不是 fail**（`tests/conftest.py:106-107,125-126`）。看到「1 skipped」要判为「未验证」，不得判为通过（04 §4.14 排除项 ②）。
2. [ ] ✅ **S-R0.1.2 判据可满足性前置检查（本版新增，防恒红判据）**
   - 动作：对卡面每条 ✅ 判据先跑一遍「在未修改代码的干净树上是否可满足」
   - 命令：`cd apps/api && grep -n '\.like(' app/services/kb.py`
   - 期望：**命中 `kb.py:342`**（解释「为什么删」的 docstring）⇒ 证明 V0.6.0 的「grep 为空」判据恒红，本卡已改用 AST 判据（S-R0.2.3）
3. [ ] 🛠 **S-R0.2.1 加第三条资产反查（精确等值，非 LIKE）**
   - 位置：`_find_source_by_anchor` 两条锚之后、`return None`（当前 `kb.py:363`）之前
   - 逻辑：`select(Source).join(ContentAsset, ContentAsset.source_id == Source.id).where(Source.type=='wechat_oa', ContentAsset.external_id == article_key).limit(1)`，且仅当 `len(article_key) >= MIN_FRAGMENT_LEN`
   - S-R0.2.1.1 import `ContentAsset`（`app.models.entities`）与 `MIN_FRAGMENT_LEN`（**从 `app.repositories.asset` 导入，不另定义**）
   - S-R0.2.1.2 `scalar_one_or_none()` 配 `.limit(1)`（与 P-4 修复同口径）
4. [ ] 🛠 **S-R0.2.2 更正 `_find_source_by_anchor` docstring（`kb.py:336-341`）**
   - 现文（假）：「无 biz 参数短链首抓后 `source.external_id=article_key`……二次入库以 article_key 锚**必然命中**」
   - 改为：说明首抓时 source 可能以**页面 biz** 为键（`_ensure_source` 规则），故 article_key 锚**不**保证命中，无参短链场景由第三条资产反查负责
5. [ ] 🛠 **S-R0.2.4 更正 `_ensure_source` docstring（`kb.py:465-470`，本版新增）**
   - 现文（假）：「biz 缺失（无参数 URL）时以 article_key 落库——短链场景二次入库**经 `_find_source_by_anchor` 的 URL 兜底可命中**」——该 URL 兜底已被 078dc30 删除
   - 改为指向第三条反查；并写明「biz 非空仍以 biz 为 external_id」这一现实（本回归的触发前提）
   - 为什么单独成步：这两句假话是**回归能进主干的直接原因**（01 F-74），删兜底的人与后来 reviewer 都是据它认为链路通
6. [ ] 🔴✅ **S-R0.2.3 常驻用例 + 反证**
   - 在 `test_kb_multisource_anchor.py` 新增 2 条：
     ① 键 `"s"`（长度 <8）不触发反查：预置 `external_id='s'` 的资产，入库 LONG_B 时断言记录里**没有** join `content_assets` 的查询
     ② 反查命中时返回资产所属源（短链 token 命中以 biz 为键的源）
   - 变异反证：删掉长度守卫 ⇒ 用例①必须红
7. [ ] ✅ **S-R0.2.5 三项读数收口**
   - 全量连库：`cd apps/api && .venv/bin/python -m pytest tests/ -q -rs --cov=app --junitxml=junit.xml` ⇒ **0 failed**
   - P-4 探针：`PROBE2 ok`
   - **AST 判据取代 grep 判据**：复用 `prove_anchor_fallback.py:820` 的 `AF-S6`（「kb 全文 AST 层不再出现任何接收者的 `.like(`」），命令：`cd apps/api && python ../docs/06_validation/evidence/EVD-V2-02/prove_anchor_fallback.py | tail -5` ⇒ AF-S6 PASS
   - 残留 LIKE 说明：`app/repositories/asset.py:66` 的 `ContentAsset.url.like` **保留不动**（01 F-73：它被 `kb.py:240 if source is not None` 挡住，与本回归无关，删除属越界改动）
8. [ ] 🗄 **S-R0.3.1（条件）索引迁移 ab1006r0a**
   - 触发条件：生产资产量门槛（由 STEP-18 或人给数）；未触发则本步跳过并在 EVD 记录「未触发」
   - `CREATE INDEX CONCURRENTLY ix_content_assets_external_id ON content_assets(external_id)`
   - S-R0.3.1.1 `down_revision` 必须指向 `ab1005w5b`，且 STEP-04 的 `ab1006c1a` 随后指向 `ab1006r0a`（03 §8 串行表）
   - S-R0.3.1.2 `EXPLAIN` 显示 Index Scan，读数入 EVD
9. [ ] 📄👤 **S-R0.4.x 治理（两项）**
   - S-R0.4.1 改 `apps/api/app/**` 的提交必须附依赖环境全量 pytest 末行读数 —— **并入 STEP-00G 的同一提交写**（所有权重叠已在此消除，见 04 §4.5）
   - S-R0.4.2 👤 执行机二选一并在 decision-log 登记：装 venv（`uv sync --extra dev` + 本地 PG），或固定把全量跑交给有依赖的沙箱

## 验收标准
- [ ] `test_be02_engine_routing.py::test_short_link_second_ingest_hits_cache_via_url_fallback` 在**依赖机**绿，且 `-rs` 输出不含该用例的 skip
- [ ] 全量连库 `0 failed`（junit 入 EVD）
- [ ] AF-S6 PASS（AST 层无 `.like(`），且 P-4 探针 `PROBE2 ok`
- [ ] 用例①配变异反证：删长度守卫 ⇒ ①红（有红档读数）
- [ ] `kb.py` 内两处假 docstring 已更正；`grep -n '必然命中\|URL 兜底' app/services/kb.py` 无残留（此判据本身先过 S-R0.1.2 可满足性检查）
- [ ] 依赖机 `ruff check app tests` rc=0 与 `gitleaks` 零新增命中，读数入 EVD
- [ ] 未改 `contracts/**`、未改 `repositories/asset.py`

## 验证命令
```bash
cd apps/api
.venv/bin/python -m pytest tests/test_be02_engine_routing.py -q -k short_link_second -rs   # 回归哨兵
.venv/bin/python -m pytest tests/ -q -rs --cov=app --junitxml=junit.xml                     # 全量门（必须 0 failed）
grep -n '\.like(' app/services/kb.py                        # 期望仅命中 docstring:342（说明文本，非代码）
python ../docs/06_validation/evidence/EVD-V2-02/prove_anchor_fallback.py | tail -5          # AF-S6 AST 判据
.venv/bin/ruff check app tests ; .venv/bin/mypy app
grep -n '必然命中\|URL 兜底' app/services/kb.py              # 期望无输出（两句假话已清）
```

## 证据路径
`docs/06_validation/evidence/EVD-V3-R0/`（本卡全部读数）。规划方留下的可参考件：`docs/任务规划V0.6.0/evidence/a9b194d/STEP-R0_regression_fix_simulated.patch`（该文件**无** DSN 字面量，可安全入库）；合并版补丁含被删占位 DSN 行，**只用于 `git apply`，不得提交**。

## 允许修改
- `apps/api/app/services/kb.py`（限定 `_find_source_by_anchor` + 两处 docstring）
- `apps/api/tests/test_kb_multisource_anchor.py`
- `apps/api/alembic/versions/ab1006r0a_*.py`（新，条件步骤）
- `docs/06_validation/evidence/EVD-V3-R0/**`

## 禁止修改
- `packages/contracts/**`、`docs/任务规划V0.7.0/contracts/**`
- `apps/api/app/repositories/asset.py`（LIKE 保留，见 S-R0.2.5）
- `apps/api/app/services/{manifest,subscription,job_worker}.py`
- 除 `ab1006r0a` 以外的任何迁移文件；`.github/workflows/*`（归 00C）
- `docs/06_validation/evidence/**/*.py` 主体（03 §4.9 冻结，例外仅迁移与 gitleaks 修复）

## 依赖与阻塞
- Depends on：无
- Blocks：STEP-02（S2.2 规范键）、STEP-06（E2E 收口）
- 阻塞条件（遇到即停并上报，不绕过）：
  1. 反查使其他用例转红 ⇒ 说明有数据依赖「源找不到」这一结果，停下逐条分析，禁止加条件绕过
  2. 需要动 `asset.py` 或 `contracts/**` ⇒ 跨所有权，转 ADR
  3. 依赖机不可得 ⇒ 标 blocked 并写明「本卡不可在无 PG 环境验收」，**不得**以 skip 冒充通过

## 建议执行档位
`sonnet`　理由：单函数改动 + V0.6.0 已有实测补丁（F-63/F-70 可套用）。

## 升级条件
升 `opus` 当且仅当：①连续 2 次验收失败（D-14 熔断）；②出现第 3 种依赖兜底的场景（即 `source=None` 的分支不止短链一种）；③需要重设计文章身份键（那是 STEP-02 的范围，应转卡而非就地扩张）。

## 预估规模
小；总计约 0.5 人日，单个三级任务均 <2h（其中 S-R0.2.2/S-R0.2.4 为分钟级文本更正）。

## V0.6.0 → V0.7.0 本卡变更（可核）
| # | 变更 | 依据 |
|---|---|---|
| 1 | 基线 a9b194d → 13acacc；确认 `apps/api/app` 未变，故 V0.6.0 实测补丁仍有效 | F-65/F-70 |
| 2 | **删除恒红判据** `grep "like(" kb.py 为空`，改为复用 AF-S6 的 AST 判据 | F-75/F-76 |
| 3 | **新增 S-R0.2.4**：更正 `_ensure_source` 的第二处假 docstring（`kb.py:468-469`） | F-74 |
| 4 | **新增 S-R0.1.2**：所有判据先做可满足性自检（防恒红/恒绿，落 B-14） | F-75 泛化 |
| 5 | **写明 skip ≠ pass**：无 PG 时该用例是 skip（`conftest.py:106-107`），必须 `-rs` 并拒收 skip | F-88 |
| 6 | 声明 `asset.py:66` 的 LIKE 保留不动（防执行者顺手扩大改动面） | F-73 |
| 7 | R0.4.1 文档步并入 00G（消除 `collaboration-discipline.md` 所有权重叠） | 04 §4.5 |
