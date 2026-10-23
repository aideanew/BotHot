# STEP-36 RSS与降级开关收尾

> 基线 main@f86811e｜状态：✅ 收口（2026-10-24，交付 head 52e8e0a 三绿 attempt 1：CI 40027812758 / CI-Windows 40027812624 / Security 40027812754；第 2 轮分片更新 r48 旧钉）｜版本 V0.18.0

| 字段 | 内容 |
|---|---|
| 1 归属 | 执行 Agent-API |
| 2 验收者 | 规划方 |
| 3 难度 / 里程碑 | 中 / M1 |
| 4 来源 | P-97、P-75、P-76、P-70；D-V18-06、D-V2-04 |
| 5 目标 | RSS 清单回退重试不再重复排队；外链过滤数跨轮可读；源清单对 RSS 显示真实 feed 地址、type 拼错会报错；按源降级开关能被打开（默认仍关） |
| 6 输入 | `app/services/subscription.py` 的 `_compute_new_manifests` 与 `:171`；`app/api/v1/subscriptions.py:88`；`app/providers/article_sources/rss.py` 的 `filtered_offsite`；`app/services/scheduler.py:207`；`app/core/config.py`；`tests/test_e2e_collection.py` 的 `asset_source_is_manifest_source` |
| 7 输出路径 | 上述源码、`app/core/metrics.py`（新增一族计数）、对应测试、契约产物（若视图形状变）、`docs/06_validation/evidence/EVD-V18-36/`（D-V18-13） |
| 10 命令 | `pytest tests/test_e2e_collection.py tests/test_rss*.py tests/test_subscription*.py -q`；`python scripts/gen_contracts.py --check`；全量 |
| 12 允许修改 | 第 7 格所列 |
| 13 禁止修改 | `kb._ensure_source` 建源口径（D-V18-06 不选②）；迁移目录 |
| 14 依赖 | 35（覆盖率余量先做出来） |
| 15 档位 | sonnet |
| 16 规模 | ≈1.0 人日 |

## 三级任务
1. [x] **S36.1** P-97（D-V18-06 ①）：ready 键减改为按规范文章键跨 source 减除；先红：复用 STEP-06 的变异（把清单合法回退成 DISCOVERED）⇒ 改前 rss 报 `30005 INGESTED → ENQUEUED`，改后六渠道全绿；`asset_source_is_manifest_source` 判据按新语义更新并写明理由
2. [x] **S36.2** P-75：`filtered_offsite` 进 `core/metrics.py` 一族计数（按 channel 标签），不进 HTTP 契约；用例断言跑一轮 RSS 后计数增加
3. [x] **S36.3** P-76：源清单视图对 `type=rss` 返回 `feedUrl`（读 `source_identifiers` 的 `feed_url`），不再把摘要塞进 `biz`；`GET /sources?type=` 取值过 `SOURCE_TYPES` 校验，非法值 422 并在原因里列出可用值（文案遵守 D-V18-05）
4. [x] **S36.4** P-70：`config.py` 加 `discovery_fallback_enabled: bool = False`，删掉 `scheduler.py` 的 `getattr` 兜底；用例：默认关只试一家，设为真时多试一家

## 完成判据（全部机器可判）
- 每项先红后绿读数
- `gen_contracts --check` rc=0
- 模块覆盖率门不降（读数入证据）
- 三绿

## 熔断
连续 2 轮验收 FAIL ⇒ 停卡交回规划方（rounds-check 机器执行，口径见 D-V18-16）。前提与现读不符 ⇒ 先登记 P 号再停，不自改卡面。
