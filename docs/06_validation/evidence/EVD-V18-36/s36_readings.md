# EVD-V18-36 RSS与降级开关收尾（执行助手）

平台 @win（Windows 10 x64，`apps/api/.venv` Python 3.12.10），开工 head `6eadbca`（STEP-35 收口批），
时间 2026-10-24（Asia/Shanghai）。卡面 = V0.18.0/steps/STEP-36-*.md。本机无 PG ⇒ 连库面以 @ci 为准。

## S36.1 ready 键跨 source 减除（P-97 / D-V18-06 ①）

- 修法：`_compute_new_manifests` 的 `ready_keys` 子查询**删掉 `ContentAsset.source_id == source_id` 过滤**
  ——ready 减跨 source 按规范文章键减（裁定 ①，代价=同键不同源的行共享一次减除）。
- **先红（@ci 实测，head 1ff09fb，run 40024327123，attempt 1，2026-10-23 21:11 UTC）**：
  新增常驻用例 `test_e2e_collection.py::test_reopened_manifest_does_not_reenqueue`（六渠道参数化，
  复用 `_round_trip` 全链到 INGESTED 后把清单合法回退成 DISCOVERED 再跑重试轮）——
  `1 failed, 2361 passed`：**rss 转 red，`assert enqueued3 == 0` 实得 2**（重开行全部重复入列），
  五个微信渠道 enqueued=0 全绿——与 P-97 登记的非对称逐字吻合（STEP-06 的 status-谓词变异同形状）。
- 改后：六渠道该用例全绿（@ci 回填见 §@ci）。
- `asset_source_is_manifest_source` 判据更新：布局事实（rss 资产挂在页面 biz 源）不变、
  断言不变；语义注释改写为"布局差异不再是守卫缺口（ready 减已跨 source）"，理由写入文件头。

## S36.2 filtered_offsite 进 metrics 族（P-75）

- `core/metrics.py` 新增 `bothot_discovery_rss_filtered_offsite_total{channel}`（Counter）+
  `record_rss_filtered_offsite(channel, count)`；`rss.py` 在 `filtered_offsite += dropped` 处同步上报。
  不进 HTTP 契约（卡面指定）。
- 先红（stash 反证，@win 本机）：暂存 metrics/rss 两文件后跑新用例 ⇒ **FAILED**（序列不存在）；
  弹回后 **2 passed**（连同 S36.4 的翻转钉）。改前佐证：e96f65a 树 grep 该序列名 0 命中。
- 用例：`test_rss_provider.py::test_filtered_offsite_is_counted_in_metrics`——断言 +3（与 `_split_offsite` 丢弃数一致）。

## S36.3 源清单视图按 type 分形状 + 取值校验（P-76）

- `list_sources`：① `source_type` 过 `SOURCE_TYPES`，拼错 ⇒ 10005 并点名可用值（D-V18-05 文案纪律）；
  ② rss 行回 `feedUrl`（读 `source_identifiers(kind='feed_url')`），不再把 128 位摘要塞进 `biz`；
  wechat_oa 行形状不变。
- 用例（test_p2_subscription.py，连库）：`test_p2_list_sources_rss_shape_returns_feed_url`
  （feedUrl=注册的 feed、行内无 biz 键）+ `test_p2_list_sources_rejects_unknown_type`
  （10005 且文案含 wechat_oa/rss）。先红：stash 服务侧改动 ⇒ 两发必红（视图无 feedUrl、无校验），
  弹回后 @ci 复算。
- `update_source` 不在本条范围（卡面只点视图与校验）。

## S36.4 降级开关补配置真身（P-70）

- `config.py` 加 `discovery_fallback_enabled: bool = False`（与卡面 S8.4.1 逐字一致）；
  `scheduler.py` 删 `getattr(settings, "discovery_fallback_enabled", False)` 兜底
  （改为直读字段——"配置项不存在"从此立即可见，不再伪装成"运营选了关"），陈旧 P-70 注释改写。
- 钉子翻转：`test_the_degradation_switch_has_no_config_field_yet`（P-70 的现状钉，其 docstring 自约
  "有人加上那一行时它会红…要一起改"）→ `test_the_degradation_switch_is_a_real_config_field`
  （判字段存在 + 缺省 False）。
- 行为两发（连库）：不传 `fallback_enabled` ⇒ 读 Settings 字段 ⇒ 默认关只试一家（`calls==["dajiala"]`）；
  `_settings(discovery_fallback_enabled=True)` ⇒ 降级发生（`calls==["dajiala","justoneapi"]`）。
- 先红（stash 反证，@win 本机）：暂存 config/scheduler 后跑翻转钉 ⇒ **FAILED**；弹回后 **passed**。

## 契约与覆盖率

- `gen_contracts.py --check`：**rc=0**（list_sources 的视图是 dict 形状、无 response_model 收紧 ⇒ 无契约产物变化）。
- 模块覆盖率门：交付 head @ci 读数见 §@ci（subscription.py 因新增视图分支 +S36.3 用例覆盖，
  预期 ≥363/412 不降）。
- SKIP_BASELINE_WIN：+6（S36.1 六渠道重开用例）+4（S36.3 两发、S36.4 两发）= 679 → **683**，随批抬起。

## @ci（推送后回填）

_（占位：交付 head 三绿 run id；先红 run 40024327123 的红读数原文（rss enqueued=2）；模块门九行读数。）_
