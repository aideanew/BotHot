# STEP-09 RSS一等信息源

| 项 | 值 |
|---|---|
| 里程碑 | M3（条件） |
| 档位 | sonnet |
| 规模 | 中（约 1 人日） |
| 依赖 | STEP-08；D-V2-03 |
| 裁决 | D-V2-03 |
| 剩余原子任务 | 4（👤 0） |
| 所有权（写） | W：app/api（订阅接口）、providers/article_sources/rss.py、services/kb.py（错误分类）、job_worker.py:100-107、docs/RSS订阅渠道.md |
| 基线 | main@a9b194d |

## 1. 目标与可证伪验收
- 订阅支持 `{type:'rss', feedUrl}`；外链不入库且可计数；畸形 URL 归为永久错误不重试。

## 2. 证据链（现状）
- rss.py:99-128 发现可用、:130-132 详情硬返 None；job_worker.py:100-107 `_is_permanent_error` 不含 MalformedUrlError。

## 3. 执行逻辑穿透
订阅 → source_identifiers(kind=feed_url) → rss provider → 过滤非 ALLOWED_HOSTS → 清单 → 入库。

## 4. 原子任务（三级编号；缩进为四级执行步）

标记：🔴 先红（写失败测试）｜🛠 实现｜✅ 验证/读数｜📄 文档｜🗄 数据/迁移｜👤 人工/裁决

### S9.1 发现层
- **S9.1.1** 🔴🛠 订阅 API 支持 rss；未知标识 ⇒ DiscoveryFailedError（不再静默当 biz）
- **S9.1.2** 🛠 发现时过滤外链并计 `filtered_offsite`

### S9.2 入库层
- **S9.2.1** 🔴🛠 `_is_permanent_error` 纳入 MalformedUrlError；`_resolve_with_retry` 不重试
- **S9.2.2** 📄 docs/RSS订阅渠道.md 标注外链预置源“仅发现，不入库”

## 5. 测试设计
- 新增约 6 条。

## 6. 停止条件与回滚
- D-V2-03 改为“入库”：另开卡评估抽取器对非微信页的质量门。

## 7. 交付证据
EVD-V2-09。

## 8. 完成定义（本卡）
所有权内 diff 与任务一致 ∧ 每个 ✅ 有读数 ∧ 本地 `ruff check app tests`（0.12.12）与 `gitleaks detect` 通过 ∧ 推送后 CI 与 Security 均 success（run id 入 EVD）∧ 复审 ≤2 轮（D-14）。
