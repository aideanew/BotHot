# STEP-08 信息源标识与按源路由

| 项 | 值 |
|---|---|
| 里程碑 | M2 |
| 档位 | opus |
| 规模 | 大（约 3 人日） |
| 依赖 | STEP-06；D-V2-04 |
| 裁决 | D-V2-04 |
| 剩余原子任务 | 6（👤 1） |
| 所有权（写） | W：迁移 ab1006c2a；entities.py（SourceIdentifier）；app/services/identifier_resolver.py（新）；providers/article_sources/base.py 与 5 个 provider（签名）；providers/discovery/registry.py；services/scheduler.py:146-169；services/manifest.py（翻页） |
| 基线 | main@65f508b |

## 1. 目标与可证伪验收
- 一个源可持有多种标识（biz/ghid/sample_url/feed_url），渠道按“所需标识 ∩ 源已有标识 ∩ 成本”选择。
- 主渠道失败时按开关降级到下一个渠道（默认关）。
- provider 协议升级为 `query_work_list(identity, cursor) -> WorkListPage`，旧签名适配器保留一个版本。

## 2. 证据链（现状）
- entities.py:59-66 Source 仅 `type/external_id/url`；scheduler.py:155-169 `resolve_default_channel` 全局单渠道。
- registry.py:33-54 渠道表、:107-128 RSS 工厂。

## 3. 执行逻辑穿透
scheduler 取订阅 → 源标识集合 → `select_channels(spec.required_identifier, cost_rank)` → provider(identity, cursor) → WorkListPage(rows, next_cursor, page_size) → manifest 以 page_size 判末页。

## 4. 原子任务（三级编号；缩进为四级执行步）

标记：🔴 先红（写失败测试）｜🛠 实现｜✅ 验证/读数｜📄 文档｜🗄 数据/迁移｜👤 人工/裁决

### S8.1 数据模型
- **S8.1.1** 🗄 迁移 ab1006c2a（down=ab1006c1a）建 source_identifiers + SQL 回填 biz；实体与 dto 同提交生成

### S8.2 标识补全
- **S8.2.1** 🔴🛠 identifier_resolver.py：从 sample_url 解析 biz、从 biz 补 ghid（有渠道支持时），测试先红

### S8.3 协议升级
- **S8.3.1** 🛠 `WorkListPage` + 新签名；5 个 provider 迁移；旧签名适配器
  - S8.3.1.1 STEP-03 契约测试仍绿
- **S8.3.2** 🛠 ManifestSyncService 以 page_size 判末页、next_cursor 翻页

### S8.4 按源路由
- **S8.4.1** 🔴🛠 `ChannelSpec.required_identifier/cost_rank`、`select_channels`；scheduler 按订阅选择；降级开关
  - S8.4.1.1 只有 biz ⇒ 不选需 ghid 的渠道
  - S8.4.1.2 降级开 ⇒ 第二渠道被调 1 次

### S8.5 上游核实
- **S8.5.1** 👤 核对 TikHub openapi（U-04），结论写 registry `verified_scope`；不符则 `implemented=False` + reason

## 5. 测试设计
- 新增约 15 条（路由矩阵参数化）。

## 6. 停止条件与回滚
- 与 STEP-10 并行时 providers/ 冲突：S10.2.2 串行于 S8.3。

## 7. 交付证据
EVD-V2-08：路由矩阵读数、迁移往返。

## 8. 完成定义（本卡）
所有权内 diff 与任务一致 ∧ 每个 ✅ 有读数 ∧ 本地 `ruff check app tests`（0.12.12）与 `gitleaks detect` 通过 ∧ 推送后 CI 与 Security 均 success（run id 入 EVD）∧ 复审 ≤2 轮（D-14）。
