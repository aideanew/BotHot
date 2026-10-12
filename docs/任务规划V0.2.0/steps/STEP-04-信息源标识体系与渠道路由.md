---
id: STEP-04
title: 信息源标识体系与按源渠道路由
priority: P1
depends: STEP-02、STEP-03；裁决 D-V2-04（S4.3 起）
parallel_with: STEP-06 的 S6.1（文件不相交）
serial_constraints: S4.2.1 晚于 S6.1（二者都写 kb.py）；S4.3.2 先于 S6.2.2（二者都写 providers/article_sources/*）
estimate: 3 人日
---

# STEP-04 信息源标识体系与渠道路由

## 目标
每个信息源记录自己拥有的标识（biz / ghid / 示例文章 URL / feed URL）；调度器按"渠道所需标识 ∩ 源已有标识 ∩ 启用且凭据就位"为**每个订阅**选择渠道；协议支持游标分页；渠道失败可（可选）降级。

## 依据（02 §D-05、§D-06、§D-13、§D-15）
- `scheduler.py::make_sync_runner` 传 `src.external_id`（biz）给任何渠道（`:138-140`）；`make_default_sync_runner` 进程级只解析一个渠道（`:155-165`）。
- 期待标识：Dajiala/JustOneAPI/TikHub=ghid（`dajiala.py:85`、`justoneapi.py:92`、`tikhub.py:93`）、Wellbyte=文章 URL（`wellbyte.py:108`）、RSS=feed（`rss.py:85-97`）；`grep -rn ghid apps/api/app/models` 为空。
- 分页：JustOneAPI `page>1` 直接空（`justoneapi.py:99-102`），`ManifestSyncService` 用 RedFox 的 20 判末页。
- 降级：`resolve_default_channel` 单选（`registry.py`）；失败只推水位（`scheduler.py:530-537`）。

## 允许修改
`apps/api/app/models/entities.py`（新增 `SourceIdentifier`）、`apps/api/alembic/versions/<新修订>.py`、`apps/api/app/services/identifier_resolver.py`（新）、`apps/api/app/services/manifest.py`（`WorkListProvider`、`sync_source`）、`apps/api/app/providers/article_sources/*.py`、`apps/api/app/providers/redfox/client.py`、`apps/api/app/providers/discovery/registry.py`、`apps/api/app/services/scheduler.py`（`make_sync_runner`、`make_default_sync_runner`）、`apps/api/app/core/config.py`（新增 `discovery_fallback_enabled`）、`apps/api/app/services/kb.py`（仅 `_persist_document` 末尾写 ghid 一行调用）、对应新测试文件
## 禁止修改
`subscription.py`（除非 S5）、`job_worker.py`、前端、文档。

## 原子任务

| 编号 | 类型 | 动作 | 验收命令 |
|---|---|---|---|
| S4.1.1 | 🗄 | 新表 `source_identifiers`（`id, source_id FK CASCADE, kind VARCHAR(16) CHECK IN ('biz','ghid','sample_url','feed_url'), value VARCHAR(512), verified_at TIMESTAMPTZ NULL`，`UNIQUE(kind, value)`，`INDEX(source_id)`） | 迁移往返 + 单头 |
| S4.1.2 | 🗄 | 回填：每个 `wechat_oa` 源写 `biz=external_id`（非空且非 article_key 形态）；`sources.url` 为 mp 文章链接者写 `sample_url` | 隔离库造数断言行数 |
| S4.2.1 | 🔴🛠 | `identifier_resolver.parse_ghid(html)`：从直抓 HTML 解析原始 id（以 S0.3 样本中实际出现的变量名为准，如 `user_name`）；`_persist_document` 成功后 upsert `ghid` | 单测：样本 HTML ⇒ `gh_` 开头；无该变量 ⇒ None |
| S4.2.2 | 🛠 | （可选）`ensure_ghid(source)`：缺 ghid 且有 `sample_url` 时调用 Wellbyte `account_history_v2`（付费），受 STEP-06 预算约束；默认关闭 | 单测：预算拒绝时不调用上游 |
| S4.3.1 | 🛠 | 协议：`SourceIdentity(biz, ghid, sample_url, feed_url)`、`WorkListPage(rows, next_cursor, total, page_size)`；`query_work_list(identity, cursor)`；旧 `(biz, page)` 适配器保留一个版本并 `DeprecationWarning` | `mypy app` 绿 |
| S4.3.2 | 🛠 | 5 provider + RSS 迁移；JustOneAPI 用 `PagingInfo.Offset/IsEnd` 作 cursor；Dajiala/RSS `next_cursor=None` | 每家契约测试（STEP-03 文件内追加）绿 |
| S4.3.3 | 🛠 | `sync_source(source_id, identity)`：以 `page.page_size` 判末页、`next_cursor` 翻页，`max_pages` 仍为硬上限 | `test_manifest_sync.py` 绿 + 新增"10 条/页不被误判末页"用例 |
| S4.4.1 | 🛠 | `ChannelSpec` 增 `required_identifier`、`cost_rank`（redfox=0 可按运营调整，rss=0，dajiala=1，wellbyte=2，justoneapi=3，tikhub=4；数值仅排序用，写入 registry 注释说明来源为 registry 计价描述） | 单测 |
| S4.4.2 | 🛠 | `select_channels(settings, identity) -> list[str]` | 单测矩阵：只有 biz ⇒ [redfox]；有 ghid ⇒ 含 dajiala；有 feed ⇒ [rss]；`discovery_default_channel` 在候选内时排首位 |
| S4.4.3 | 🛠 | `make_sync_runner`：每订阅加载 identity → `select_channels` → 取首个；`DiscoveryFailedError` 且 `discovery_fallback_enabled` ⇒ 试下一个，最多 2 次；provider 实例按渠道名缓存复用 | S4.4.4 绿 |
| S4.4.4 | 🔴✅ | 测试：首渠道抛错 + 降级开 ⇒ 第二渠道恰调用 1 次；降级关 ⇒ 0 次且水位按基准推进（与现语义一致） | 绿 |
| S4.5.1 | 👤 | 核对 `api.tikhub.io/openapi.json` 发现端点（U-04）；结论写入 registry `verified_scope`；端点已下线则 `implemented=False` + `reason` | 人工；registry diff |
| S4.6.1 | 👤 | 每个准备启用的付费渠道做一次活体（1 个号、1 页），录制响应替换 STEP-00 样本，记成本 | 人工；EVD-V2-04 |

## 完成定义
S4.4.4 绿；`describe_channels` 输出不变（向后兼容）；对仅有 biz 的存量订阅行为与现状逐字一致（RedFox）。

## 回滚
`discovery_fallback_enabled=False` 即回到"首选渠道"语义；协议适配器保留旧签名；迁移可 downgrade。

## 风险
- 多渠道多计费口径 ⇒ 降级默认关闭，直至 STEP-06 预算上线。
- ghid 解析依赖页面变量名，微信改版即失效 ⇒ 解析失败只是"不写 ghid"，不影响入库。
