# STEP-02 文章身份规范键-P3

> 基线 main@61358c3｜状态：✅ Done（2026-10-16 判定，读数见下一段；卡内历史行文按 `3a67e96`/`61358c3`
> 时点保留，不回改）——**S2.2.1 + S2.2.2 已交付**：
> `article_identity.normalize_url` / `canonical_article_key`（ADR-0011 三分支 `b:`/`s:`/`h:`），
> ADR §3 五条不变量逐条有用例（`tests/test_article_identity.py` 现 24 条、模块覆盖 100% `@win`），
> 读数与两处被既有证明件抓出的缺陷见 `EVD-V2-02/s221_canonical_key.md`。
> **第二轮独立验证抓出更重的一条**：两支"无条件采纳"会产出契约 `ArticleKey` 拒收的键
> （`b:MjM5:1:1` 段太短、`s:abc` 短于 minLength、136 字符超 maxLength ⇒ PG `varchar(128)` 直接 DataError，
> 最坏是 `__biz=AAAAAAAA:B&mid=C` 与 `__biz=AAAAAAAA&mid=B:C` **冒名成同一个键**）；
> 已改为"整键形状验证后采纳，否则降级 `h:`"，新增不变量④与 3 条变异反证，
> 并在 ADR-0011 追加 §8 实施期更正（§3.1/§6 的"≥8""≤128 零迁移"按伪码字面实现时为假）。
> **规范键已接上生产者**（2026-10-16 第二批）：S2.2.3 以「`kb._article_key` 薄委托真源」实现
> （5 个取键点全经它，故不需逐处替换），S2.3.3 让 `batch_ingest` 委托同一真源并加漂移守卫
> （`tests/test_batch_ingest_key_drift.py`，两向断言），S2.3.1 收掉测试里的两份算法复刻，
> S2.2.4 加短链旧裸 token 的**只读**兜底（不改写存量，回填仍归 STEP-07 / 裁决 D-V9-01），
> S2.2.3.3 的 P-3 探针转正为 `test_two_distinct_long_links`（同号两篇必须 2 次抓取、同篇两书写不得多抓）。
> 读数 `@win`：调用面全集 **270 passed / 63 skipped**、ruff 与 mypy(112 files) 干净、collect 1278 无错。
> **同卡下游又炸出一条**（`@ci` run 38908795127 红，非末次提交内容所致而是恒真条件的并发后果）：
> `_save_short_link` 先查后插而无 savepoint ⇒ 两个并发首抓都查空、后发者撞 `uq_shortlink_key`
> 冒成 500。已按 `_ensure_source` 的 T2.7 兜底同形修掉，加 barrier 钉死交错的连库用例
> 与本机确定性证据件 `EVD-V2-02/prove_shortlink_race.py`（`--self-test` PASS，摘 savepoint 必红）。
> **`@ci` 已回读成立**：`d2f536c` run 38918538114 与 `8cc7dea` run 38920557247 的 `CI` 均 success
> （后者 backend `1305 passed / 6 skipped`、skip 门禁 `pg_unreachable=0` ⇒ 两条新连库用例真跑），
> 读数与反面写在 `10-执行过程-独立执行段第三批.md` §7.6。
> 教训写在 `10-执行过程-独立执行段第三批.md` §7.2：恒真这件事我上一批**读到过却没走完**，
> 只当成 ADR 前提失效记录，没推出"每个短链首抓都落一行 ⇒ 并发量变常态"。
> **这条读数不可复核**（记录里没留文件清单，现读 grep 只得到 11 个文件）——按纪律标注为过期，
> 不要再引用它；可复核的本段读数见 `09-执行过程-独立执行段第二批.md` §7.6。
> **`@ci` 回读为红**（run 38889655890：`6 failed / 1266 passed / 6 skipped`）：S2.3.1 只收掉了测试里的
> 算法**复刻函数**，漏了同批的键**常量**，六条红全是"拿旧键查新行"；已改为派生（`8a95739`），
> `CI` run 38891816054 = success ⇒ main 回绿。
> **同轮独立验证另抓出一条生产缺陷**：第三条锚把规范键与旧裸 token 两支候选并成一次无序
> `IN(...).limit(1)`，两键空间分属不同源时可跨源冒名（旧末段键非单射）——改逐键有序
> （裁决 **D-V9-02**），并补 `AF-S8`/`AF-B8` 两条证据件判据与两条连库用例；
> 证据件的假会话此前没有 `.join`，第三条锚一进去就抛 AttributeError ⇒ **AF-B6 自 S2.2.4 起一直红在工具上**，
> 已修（`--self-test` 现为 49/49 发跑成、判据 21 条全绿）。D-V9-01 的后果清单不完整，补登记为 **D-V9-03**。
> **63 条 skip 覆盖的正是本次改变行为的路径** ⇒ 本卡 Done 曾待 `@ci` ubuntu（D-V4-01）。
> **`@ci` 已回读并成立**（2026-10-16，main@`925a85e`：`CI` run 38899498196 = success，
> backend `1274 passed / 6 skipped`、覆盖率 79.90%、`SKIP_BASELINE=6` 未涨 ⇒ 本卡新增的两条
> 连库用例是真跑不是凑数；`Security` run 38899498399 = success；`CI-Windows` 与本卡无关，红在 U-23）。
> 卡面 S2.3.2 的出口条件（P-3 复跑达修复后期望、全量 0 failed、ruff/mypy/CI 双绿）据此成立，
> **本卡状态改判 ✅ Done**；仍开的两件事不在本卡范围内：存量行的键回填归 **STEP-07**
> （输入清单见 D-V9-01 与 D-V9-03），兼容层残余的旧键命中风险也在那一条里收口。
> 另记一条 ADR 前提随迁移失效（映射表写入条件 `final_key != short_key` 现在恒真），
> 处置见 `09-执行过程-独立执行段第二批.md` §6.3，不改已签 ADR 正文。

| 字段 | 内容 |
|---|---|
| 1 归属（执行者） | 执行Agent |
| 2 验收者（与执行者分离） | 规划方(Hark)，只输出 PASS/FAIL/UNKNOWN |
| 3 难度 / 里程碑 | 高 / M1 |
| 4 来源 | V0.7.0 docs/任务规划V0.7.0/steps/STEP-02-文章身份规范键-P3.md |
| 5 目标 | 同来源卡；本版不改目标 |
| 6 输入 | 来源卡『输入』+ 本版 01 事实基线（行号以 61358c3 现读为准） |
| 7 输出路径 | 同来源卡 |
| 8 三级任务 | 沿用来源卡编号 Sx.y.z，全文见来源卡；本版未改动 |
| 9 验收 | 来源卡验收 + 当前基线 CI 双绿 + skip≠pass |
| 10 命令 | 来源卡命令；全量回归 `cd apps/api && uv run pytest -q -rs` |
| 11 证据 | docs/任务规划V0.8.0/evidence/61358c3-02/ |
| 12 允许修改 | 同来源卡所有权矩阵（本版 04 §4） |
| 13 禁止修改 | 他卡所有路径；迁移目录（需 DDL 停转 ADR）；历史规划结论 |
| 14 依赖 / 阻塞 | RV、01 / D-V3-01 |
| 15 档位 | T2 |
| 16 升级条件 / 规模 | 来源卡行号漂移>3 处或判据不可满足 ⇒ 停并上报规划方 / ≈1.5 人日 |

## 本版（V0.7.0 → V0.8.0）变更

- 基线改为 61358c3；执行前先现读行号，禁止照抄来源卡读数。
- 所有新增证据件入库前必须 gitleaks 零新增（G-PLAN）。
- 依赖更新为：RV、01。

## V0.9.0 → V0.10.0 本卡变更（基线 main@81cb997）

- 本版无实质变更；执行前现读行号（基线 81cb997，自 53ebc4a 起业务代码零改动）。

## 裁决已签（V0.11.0 第四节第 2 步 · 2026-10-15 12:04）
| 项 | 变化 |
|---|---|
| D-V2-01 | 规范键已定（ADR-0011）：`b:{biz}:{mid}:{idx}` / `s:{token}` / `h:{sha256[:32]}`；不变量含「任何输入键不等于 `s`、且长度 ≥8」，正是 STEP-R0 长度守卫要一直承担到回填完成的原因 |
| 验收面 | 本卡 Done 只能由 `@ci` **ubuntu-latest** 判定；`@win` 读数只算开发烟测，`@linux` 为依赖机本地验证 |
| 标签 | 依 D-V6-01，本卡 `@dep` 已全部改写为 `@linux`/`@ci` |

---

## V0.13.0 本卡重开：S2.4 数字段规范化（基线 main@314d7f2，新增 2 个三级任务 / 0.5 人日）

> 状态从 ✅ 改为 🟡：S2.1–S2.3 的交付仍然成立，**只新增 S2.4**。执行者：执行 Agent；档位 sonnect（升级条件见下）。

### 证据
`evidence/314d7f2/probe_leading_zero.txt`（`@linux` 现跑）：
```
...&mid=2650&idx=1&sn=abc   -> b:MzA5NzY4ODk2Mg==:2650:1
...&mid=02650&idx=01&sn=abc -> b:MzA5NzY4ODk2Mg==:02650:01
```
同一篇文章（微信服务端把 `mid`/`idx` 当整数解析）得到**两个键**，违反本卡不变量①"同文同键"。原因：`app/services/article_identity.py:86-87` 原样取字符串，`:163-164` 原样拼接，无数字规范化。上游确实会出现带前导零的形态吗？`证据不足`（无生产样本）；但键函数的不变量不应依赖上游"恰好不带零"。

### 反证
- 规范化会不会让两篇不同的文章撞键？只有当 `mid` 本身不是十进制整数时才可能 ⇒ S2.4.1 只对 `str.isdigit()` 为真的值做 `str(int(x))`，其余原样保留（再由现有 `ArticleKey` pattern 把关）。
- 存量键会不会失配？存量里若真有前导零键（`证据不足`，无生产只读访问），会与新键并存——与 D-V9-01 已签的"存量不迁移、兼容层只读兜底、清理归 STEP-07"同一处理口径，**不新增裁决**，只在 STEP-07 输入清单加一行。

### Execution Steps
1. [x] **S2.4.1** 先红：`tests/test_article_identity.py`（或现有规范键测试文件）新增参数化用例 `mid=02650&idx=01` 与 `mid=2650&idx=1` 同键、`mid=0` 与 `mid=00` 同键、`mid=12a`（非数字）原样保留；在 314d7f2 上红。然后在 `parse_wechat_url` 返回前对 `mid`/`idx` 做 `_canon_int(x) = str(int(x)) if x.isdigit() else x`（`idx` 缺省值 `'1'` 不变）
2. [x] **S2.4.2** 漂移守卫：S2.3.3 的"单一键真源"守卫仍绿；`canonical_article_key` 的四条不变量测试全绿；在 `docs/03_solution/decisions/adr-0011-canonical-article-key.md` 末尾追加一段"数字段规范化"（一段话 + 本证据路径）；STEP-07 卡输入清单加"前导零存量键（若有）"

### 验收标准
- [x] 新用例 314d7f2 红、本卡提交绿（本机改前 `2 failed, 1 passed`；改后 `test_article_identity.py` 29 passed）
- [x] `python -c "from app.services.article_identity import canonical_article_key as k; assert k('https://mp.weixin.qq.com/s?__biz=MzA5NzY4ODk2Mg==&mid=02650&idx=01')==k('https://mp.weixin.qq.com/s?__biz=MzA5NzY4ODk2Mg==&mid=2650&idx=1')"` 退出码 0
- [ ] 真库全量 `failed = 0`；`@ci` `CI` success

### 验证命令
```bash
cd apps/api && . .venv/bin/activate
python -m pytest tests/ -q -k "article_identity or canonical or article_key"
```

### 允许修改
`apps/api/app/services/article_identity.py`、规范键测试文件、`adr-0011-canonical-article-key.md`（追加段）、`docs/任务规划V0.13.0/steps/STEP-07-*.md`（输入清单一行）、`docs/06_validation/evidence/EVD-V13-02/**`
### 禁止修改
`apps/api/app/services/kb.py`、`apps/api/alembic/**`、`packages/contracts/**`（`ArticleKey` pattern 不变）
### 依赖与阻塞
Depends on：无（与 04 不共享文件：04 改 `models/entities.py` 与迁移，本步只改 `article_identity.py`）　Blocks：07
### 升级条件
发现生产里已有大量前导零键（STEP-07 审计读数）⇒ 升 opus 重评 D-V9-01 的"不迁移"
### 预估规模
小　2 个三级任务，合计 ≈0.5 人日
