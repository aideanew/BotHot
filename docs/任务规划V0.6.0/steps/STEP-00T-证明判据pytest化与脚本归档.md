# STEP-00T 证明判据pytest化与脚本归档

| 项 | 值 |
|---|---|
| 里程碑 | M1（并行支线） |
| 档位 | sonnet |
| 规模 | 中（约 1 人日） |
| 依赖 | STEP-00C（CI 能跑 pytest）、STEP-00G（冻结生效） |
| 裁决 | — |
| 剩余原子任务 | 7（👤 0） |
| 所有权（写） | W：apps/api/tests/test_env_isolation.py、test_kb_longlink_ingest.py、test_article_identity.py、tests/test_identity_single_source.py（新）；docs/06_validation/evidence/EVD-V2-00R/README.md、EVD-V2-02/README.md；Makefile（evidence-check 调用列表） |
| 基线 | main@a9b194d |

## 1. 目标与可证伪验收
- BD-1…BD-16、NR-1…NR-17 每条判据被归入三类之一：已迁 pytest / 已有等价 pytest / 不再需要（附理由），覆盖率 100%。
- 有回归价值的判据全部在 `apps/api/tests` 内、随 CI 运行，且每条都做过变异反证（破坏实现 ⇒ 红）。
- 证明脚本标注归档（不删除，遵守禁 `git rm`），evidence-check 不再调用已迁移脚本，门禁耗时下降。

## 2. 证据链（现状）
- 6,801 行脚本（a9b194d，`wc -l`）：EVD-V2-00R/prove_net_isolation.py 与 EVD-V2-02 下 7 个 .py（新增 prove_anchor_fallback.py 1,087 行；replay_s213.py 本轮 +810 行）。AF-* 判据的行为面已有真实 pytest 对应（test_kb_multisource_anchor.py、test_asset_fragment_guard.py），可直接归为「已有等价 pytest」。
- `grep -rlE "BD-[0-9]+|NR-1[4-7]" apps/api/tests` 无结果；tests 内仅 test_env_isolation.py:19-20 引用 NR-4/NR-6/NR-12。
- ci.yml 无对这些脚本的调用。

## 3. 执行逻辑穿透
证明脚本 = stdlib + AST/文本扫描 + 子进程重放，判定对象是“测试夹具与 3 行委托是否如所述”。等价的 pytest 写法：
- 环境类（NR-*）→ monkeypatch + 子进程/`os.environ` 断言（已有 test_env_isolation 骨架）；
- 委托/唯一定义类（BD-*）→ `inspect`/`ast` 解析 `app.services.kb` 与 `article_identity`，断言 `_biz_from_url` 只调用 `parse_wechat_url` 且全仓只有一处定义；行为类直接用 fixtures/wechat_urls.py 参数化。

## 4. 原子任务（三级编号；缩进为四级执行步）

标记：🔴 先红（写失败测试）｜🛠 实现｜✅ 验证/读数｜📄 文档｜🗄 数据/迁移｜👤 人工/裁决

### S0T.1 盘点
- **S0T.1.1** 📄 建迁移清单表（判据 ID / 被证对象 file:line / 现有 pytest 等价 / 分类 / 目标用例名），范围含 BD-*、NR-*、AF-*、O 段
  - S0T.1.1.1 从脚本中提取 check("…") 标签自动生成初表
  - S0T.1.1.2 人工补分类与理由

### S0T.2 迁移
- **S0T.2.1** 🔴🛠 NR-14/15/17 → test_env_isolation.py 新用例（环境写入通道全集、禁平台读数）
  - S0T.2.1.1 每条先在临时破坏夹具下确认红
- **S0T.2.2** 🔴🛠 BD 行为类（`__biz`/`biz` 优先级、`+` 字面、非 str 入参、别名）→ test_kb_longlink_ingest.py / test_article_identity.py 参数化
- **S0T.2.3** 🔴🛠 BD 结构类（唯一定义、委托活绑定、证明面越出一跳）→ 新建 test_identity_single_source.py（ast 扫描 app/）
  - S0T.2.3.1 变异：在 kb.py 复制一份私有解析 ⇒ 红
- **S0T.2.4** ✅ 迁移后全量 pytest 双环境 0 failed，新增用例数与清单“已迁”行数一致

### S0T.3 归档
- **S0T.3.1** 📄 两个 EVD README 顶部标注“已归档：判据迁至 tests/…（见清单）”，脚本保留
- **S0T.3.2** 🛠 evidence-check 移除已迁移脚本调用；S0G.3.2 冻结基线保持（脚本不再增长）

## 5. 测试设计
- 新增约 20–30 条 pytest（以清单为准）；全部纯函数或 monkeypatch，不连库，CI 离线可跑。

## 6. 停止条件与回滚
- 某判据无法用 pytest 表达（如依赖宿主网络栈）：标“不再需要/环境专属”，写明理由，不再保留脚本作为门禁。

## 7. 交付证据
EVD-V2-00T：迁移清单、变异反证输出、evidence-check 前后耗时。

## 8. 完成定义（本卡）
所有权内 diff 与任务一致 ∧ 每个 ✅ 有读数 ∧ 本地 `ruff check app tests`（0.12.12）与 `gitleaks detect` 通过 ∧ 推送后 CI 与 Security 均 success（run id 入 EVD）∧ 复审 ≤2 轮（D-14）。
