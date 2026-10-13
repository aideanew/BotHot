# STEP-03 渠道行契约归一

| 项 | 值 |
|---|---|
| 里程碑 | M1 |
| 档位 | sonnet |
| 规模 | 中（约 1.5 人日） |
| 依赖 | STEP-01；S3.3.3 另依赖 S2.2.2 |
| 裁决 | — |
| 剩余原子任务 | 10（👤 0） |
| 所有权（写） | W：apps/api/app/providers/article_sources/{dajiala,justoneapi,tikhub,wellbyte,rss}.py；apps/api/app/services/manifest.py（_map_row/_parse_time/_first_str）；apps/api/tests/test_provider_contract.py（新）、test_rss_provider.py |
| 基线 | main@65f508b |

## 1. 目标与可证伪验收
- P-1：dajiala/justoneapi/tikhub/wellbyte 样本行经 `_map_row` 全部非 None；RSS RFC 822 时间可解析。
- 所有 provider 输出 `WorkListRow`；缺 id 行不再静默丢弃（兜底规范键 + 计数）。
- 新增渠道只需加样本即被参数化契约测试覆盖（扩展性）。

## 2. 证据链（现状）
- 行构造：dajiala.py:111-119、justoneapi.py:136-144、tikhub.py:141-149、wellbyte.py:156-163——均无 id。
- manifest.py:51-55 `_ID_KEYS`；:144-146 缺 id ⇒ `return None`；:96 `_parse_time` 不支持 RFC 822。
- rss.py:222-224 自带 id；P-1 读数：dajiala/justoneapi → None、rss `publish_time=None`。
- 样本：apps/api/tests/fixtures/provider_payloads/ 9 个。

## 3. 执行逻辑穿透
provider.query_work_list → rows → ManifestSyncService.sync_source(manifest.py:174) → `_map_row` → `_upsert`。修复在两端同时设防：生产端（provider 产出 `id`）+ 消费端（`_map_row` 优先 `id`、缺失兜底），任一端回退都不会再整页丢失。

## 4. 原子任务（三级编号；缩进为四级执行步）

标记：🔴 先红（写失败测试）｜🛠 实现｜✅ 验证/读数｜📄 文档｜🗄 数据/迁移｜👤 人工/裁决

### S3.1 先红：全渠道契约测试
- **S3.1.1** 🔴 test_provider_contract.py：对 provider_payloads 全部样本参数化，断言每行含 id/url/title 且经 `_map_row` 非 None
  - S3.1.1.1 改前期望：4 家付费红、redfox 绿
  - S3.1.1.2 参数化 id 用样本文件名，新样本自动纳入
- **S3.1.2** 🔴 test_rss_provider.py 增 3 条：RFC 822、带时区缩写、非法时间 ⇒ None 但行保留

### S3.2 生产端：各 provider 输出 WorkListRow
- **S3.2.1** 🛠 dajiala 行增 `id`（上游 id 优先，否则规范键）+ `publishTime` 统一键名
  - S3.2.1.1 S3.1.1[dajiala] 转绿
- **S3.2.2** 🛠 justoneapi 同上（`$.data.MsgList.Msg` 层级按样本）
- **S3.2.3** 🛠 tikhub 同上（端点核实属 S8.5.1，本步只按样本）
- **S3.2.4** 🛠 wellbyte 同上

### S3.3 消费端：manifest 兼容与防御
- **S3.3.1** 🛠 `_parse_time` 增 RFC 822（`email.utils.parsedate_to_datetime`），统一转 UTC
  - S3.3.1.1 S3.1.2 转绿
- **S3.3.2** 🛠 `_map_row` 优先读 `id`，`_ID_KEYS` 保留为兼容别名
  - S3.3.2.1 S3.1.1 全绿
- **S3.3.3** 🛠 缺 id 防御兜底：`id = canonical_article_key(url)`、`id_fallback=True`、计数并 WARN 日志（不再 return None）
  - S3.3.3.1 单测：构造缺 id 行 ⇒ 入清单且计数 +1

### S3.4 验收
- **S3.4.1** ✅ P-1 复跑全部非 None；4 家 provider 模块覆盖率 ≥80%；全量双环境 0 failed；CI 双绿

## 5. 测试设计
- test_provider_contract.py（样本数 × 3 断言）；test_rss_provider.py +3；manifest 兜底 +2。

## 6. 停止条件与回滚
- 样本形状与活体上游不符（R-1）：本步以样本为准完成；活体核实留 S8.5.1，不在本步猜测上游字段。

## 7. 交付证据
EVD-V2-03：P-1 前后读数、覆盖率表。

## 8. 完成定义（本卡）
所有权内 diff 与任务一致 ∧ 每个 ✅ 有读数 ∧ 本地 `ruff check app tests`（0.12.12）与 `gitleaks detect` 通过 ∧ 推送后 CI 与 Security 均 success（run id 入 EVD）∧ 复审 ≤2 轮（D-14）。
