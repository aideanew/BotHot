---
id: STEP-03
title: 渠道行契约归一（provider 行 → manifest 的唯一形状）
priority: P0
depends: STEP-01；`_map_row` 修改须在 STEP-02 S2.3.1 合入后
parallel_with: STEP-02
estimate: 1.5 人日
---

# STEP-03 渠道行契约归一

## 目标
所有 `implemented=True` 的发现渠道产出的每一行都能被 `_map_row` 接受，`publish_time` 为带时区时间；新增渠道若不满足契约，测试立即变红。

## 依据（02 §D-03、§D-04）
- `manifest.py::_ID_KEYS`（`:51`）与 4 家行构造（`dajiala.py:111-119`、`justoneapi.py:135-143`、`tikhub.py:140-148`、`wellbyte.py:155-162`）无交集；探针 P-1：`dajiala -> None`、`justoneapi -> None`。
- RSS2 `pubDate` RFC 822 → `fromisoformat` 失败（`manifest.py:114`）；探针 P-1：`rss -> publish_time: None`。
- 4 家 client 覆盖率 16–22%、零测试（01 §1.2.3）。

## 允许修改
`apps/api/app/providers/article_sources/{base,dajiala,justoneapi,tikhub,wellbyte,rss}.py`、`apps/api/app/services/manifest.py`（仅 `_parse_time`、`_map_row`、`ManifestSyncReport` 新增计数字段）、`apps/api/tests/test_provider_contract_*.py`（新）、`apps/api/tests/test_rss_provider.py`（仅新增用例）、`apps/api/tests/fixtures/provider_payloads/**`（STEP-00 已建，可补样本）
## 禁止修改
`registry.py`（STEP-04）、`scheduler.py`、`kb.py`、`subscription.py`、`models/**`。

## 原子任务

| 编号 | 类型 | 动作 | 验收命令 |
|---|---|---|---|
| S3.1.1 | 🛠 | `base.py` 定义 `class WorkListRow(TypedDict, total=False)`：`id: Required[str]`、`url: Required[str]`、`title: Required[str]`、`publish_time: datetime | None`、`digest: str`、`author: str`；`ArticleSourceProvider.query_work_list` 返回类型改为 `list[WorkListRow]`；docstring 写明 `id` 语义 | `mypy app` 绿 |
| S3.2.1 | 🔴 | `test_provider_contract_dajiala.py`：`httpx.MockTransport` 回放 `fixtures/provider_payloads/dajiala.json` ⇒ 每行 `_map_row(row)` 非 None 且 `publish_time.tzinfo` 非空 | 改前 FAIL |
| S3.2.2 | 🔴 | 同上 justoneapi（form 编码请求体断言：`token`、`ghid` 两键） | 改前 FAIL |
| S3.2.3 | 🔴 | 同上 tikhub；U-04 未关闭前整文件 `pytest.mark.xfail(strict=True, reason="U-04 端点待核")` | 改前 xfail 也需"按预期失败" |
| S3.2.4 | 🔴 | 同上 wellbyte（断言 JSON body 而非 form，对应 registry 记录的 40001 坑） | 改前 FAIL |
| S3.2.5 | 🔴 | `test_rss_provider.py::test_rss2_pubdate_maps_to_aware_datetime` | 改前 FAIL |
| S3.2.6 | 🔴 | `test_provider_contract_all.py`：参数化 `registry.CHANNELS` 中 `implemented=True` 的渠道名，要求 `fixtures/provider_payloads/{name}.json|xml` 存在且通过同款断言（redfox 也纳入） | 改前 FAIL（4 家不过） |
| S3.3.1 | 🛠 | 4 个 client 补 `id`：上游行若带稳定标识（以样本为准，如 JustOneAPI/Wellbyte 的 `AppMsg.MsgId`+`ItemIndex`，TikHub `comm_msg_info.id`）则拼为 `{msgid}_{idx}`；否则 `canonical_article_key(url)` | S3.2.1–S3.2.4 绿 |
| S3.3.2 | 🛠 | provider 内 epoch → `datetime.fromtimestamp(ts, UTC)`；`_map_row`/`_parse_time` 接受 `datetime` 原样返回（无时区补 `UPSTREAM_TZ`） | 同上 |
| S3.3.3 | 🛠 | `_parse_time` 在 `fromisoformat` 失败后尝试 `email.utils.parsedate_to_datetime` | S3.2.5 绿 |
| S3.3.4 | 🛠 | `_map_row` 防御兜底：缺 id 有 url ⇒ `external_id=canonical_article_key(url)`；`ManifestSyncReport` 增 `id_fallback` 计数并在日志输出 | 单测：缺 id 行不再 skip 且 `id_fallback==1` |
| S3.4.1 | ✅ | 覆盖率与探针 | `pytest tests -q --cov=app.providers.article_sources --cov-report=term` 4 个 client 各 ≥ 80%；`evidence/probe_row_mapping.py` 无 `None` |

## 完成定义
S3.2.* 绿（tikhub 允许 strict xfail）；4 client ≥ 80%；探针 P-1 全部可用。

## 回滚
`git revert`；无数据迁移。已按旧口径（全 skip）写入的数据不存在，故无存量问题。

## 风险
- 样本形状来自代码注释与 registry 记录，**非本轮活体**；首次在生产启用某渠道前，按 STEP-04 S4.5 / STEP-06 的人工验收段录制一次真实响应替换样本。
- `id` 的选择影响 manifest 唯一键：同一篇若先由 RedFox（workUuid）后由 Dajiala（msgid_idx）发现，会产生两条清单行；STEP-02 的 `article_key` 对齐保证它们**不会重复入库**（Diff 以 article_key 判定）。
