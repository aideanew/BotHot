# STEP-03 渠道行契约归一

> 基线 main@61358c3｜状态：🟡 进行中（2026-10-16 起）——**S3.1 / S3.2 / S3.3 已交付**：
> 新 `tests/test_provider_contract.py`（按样本名参数化 + 样本认领守卫 + 缺 Key 显式失败），
> 四家付费 provider 的清单行加规范键 `id`（真源 `canonical_article_key`，时间键统一 `publishTime`），
> `_ID_KEYS` 把 `id` 排最前、`_map_row` 缺 id 不再丢整行而是兜底建键 + `id_fallback` 计数 + WARNING，
> `_parse_time` 接 `email.utils.parsedate_to_datetime`（RFC 822 / GMT / EST / 无时区按 GMT）。
> 先红的读数与"实现前就暴露的三处卡面口径差"见 `10-执行过程-独立执行段第三批.md` §6.1–§6.3。
> **S3.4.1 未达，不遮**：卡面要「4 家 provider 模块覆盖率 ≥80%」，现读 43–52%，
> 缺口在 detail/search/错误映射，已发布为 **P-14**（带读数命令与反证要求）。
> 独立验证在本批提交前抓出两处真缺陷并当场修掉：生产端用未 strip 的 URL 算键会与消费端
> 算出**两个**身份（同一键空间的冒名，STEP-02 同族）；`id_fallback` 标记混在模型字段里
> "靠调用方记得 pop"（插入路径有声、更新路径无声）——现改由 `_row_identity` 单点判。
> 另有一项**只登记不改**：RFC 822 无时区按 GMT、ISO 无时区按 `Asia/Shanghai`，
> 这是两套上游各自的规范，改哪一边都要活体样本或真库来判。
> 两条被改到的连库用例（`test_manifest_sync.py` 的 skipped 语义）本机只 skip，判定面在 `@ci`：
> **已回读**（run 38904912095 = success，backend `1303 passed / 6 skipped`、覆盖率 81.61%、
> `skip 门禁 total_skipped=6 baseline=6 pg_unreachable=0` ⇒ 连库真跑），
> `Security` run 38904912113 = success，`CI-Windows` run 38904912154 红在同点 U-23。
> **本卡状态：S3.1–S3.3 ✅ 已确认，S3.4.1 ⚪ 未达（P-14）** ⇒ 卡头保持 🟡 直到覆盖率门过线。
> 三处口径更正：所有权表里的 `article_sources/redfox.py` **不存在**（RedFox 在
> `app/providers/redfox/client.py`，且它的行是上游原样透传，本卡不改它的键名）。

| 字段 | 内容 |
|---|---|
| 1 归属（执行者） | 执行Agent |
| 2 验收者（与执行者分离） | 规划方(Hark)，只输出 PASS/FAIL/UNKNOWN |
| 3 难度 / 里程碑 | 中 / M1 |
| 4 来源 | V0.7.0 docs/任务规划V0.7.0/steps/STEP-03-渠道行契约归一.md |
| 5 目标 | 同来源卡；本版不改目标 |
| 6 输入 | 来源卡『输入』+ 本版 01 事实基线（行号以 61358c3 现读为准） |
| 7 输出路径 | 同来源卡 |
| 8 三级任务 | 沿用来源卡编号 Sx.y.z，全文见来源卡；本版未改动 |
| 9 验收 | 来源卡验收 + 当前基线 CI 双绿 + skip≠pass |
| 10 命令 | 来源卡命令；全量回归 `cd apps/api && uv run pytest -q -rs` |
| 11 证据 | docs/任务规划V0.8.0/evidence/61358c3-03/ |
| 12 允许修改 | 同来源卡所有权矩阵（本版 04 §4） |
| 13 禁止修改 | 他卡所有路径；迁移目录（需 DDL 停转 ADR）；历史规划结论 |
| 14 依赖 / 阻塞 | 01 / 无 |
| 15 档位 | T2 |
| 16 升级条件 / 规模 | 来源卡行号漂移>3 处或判据不可满足 ⇒ 停并上报规划方 / ≈1.5 人日 |

## 本版（V0.7.0 → V0.8.0）变更

- 基线改为 61358c3；执行前先现读行号，禁止照抄来源卡读数。
- 所有新增证据件入库前必须 gitleaks 零新增（G-PLAN）。
- 依赖更新为：01。

## V0.9.0 → V0.10.0 本卡变更（基线 main@81cb997）

- 本版无实质变更；执行前现读行号（基线 81cb997，自 53ebc4a 起业务代码零改动）。
