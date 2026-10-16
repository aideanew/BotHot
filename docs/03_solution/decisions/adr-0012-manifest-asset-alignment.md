---
id: ADR-0012
type: decision
title: 清单↔资产键对齐与清单状态机
status: accepted
owner: architecture
created: 2026-10-16
updated: 2026-10-16
related: [D-V2-02, D-V3-01, D-V2-01, ADR-0011, STEP-01, STEP-04, STEP-07]
---

# ADR-0012：清单↔资产键对齐与清单状态机

本 ADR 记录 **D-V2-02 与 D-V3-01 已签入的两条裁决**（签字列：
"用户授权代选 / 2026-10-15"，见 `decision-log.md` D-V2-02 / D-V3-01 行），
把它们写成可实现、可测的形状与不变量。**它不新增决策**；若与裁决文本冲突，以台账为准并回来改本文件。
键形本身不在此决定，见 ADR-0011。

## 1. 背景与被否证的现状（实测锚）

同一个 `external_id` 列名，在两张表里装的是**互不相交的两个键空间**：

| 位置 | 装什么 | 写入点 |
|---|---|---|
| `article_manifests.external_id`（`app/models/entities.py:108`，唯一键 `:115`） | 渠道上游稳定 id（`workUuid` 等） | 取键 `app/services/manifest.py:144` → 入 dict `:156` → 唯一构造点 `:255` |
| `content_assets.external_id`（`entities.py:127`，注释就写着 `# article_key`，唯一键 `:144`） | `_article_key(url)` 派生的文章键 | `app/services/kb.py:461` |
| `job_items.external_id`（`entities.py:216`） | 从清单行**原样透传**的渠道 id | `subscription.py:849`、`repositories/job.py:197` |

> 干扰项（第五轮验证踩过）：`sources.external_id`（`entities.py:62`，注释 `# 公众号 biz`，
> 写点 `subscription.py:130`、查询点 `:124`）是**账号级**键空间，与上面三行的**文章级**键空间
> 不同层，也不是本 ADR 要对齐的对象。它和 `article_manifests.external_id` 同名不同义，
> 拿它当清单写入点会把"三层无共同键"这个结论讲错。

⇒ 后果（P0-2）：**清单、作业、资产三层没有共同的键可 join**。Diff 只能拿
`(source_id, external_id)` 判"这条清单见过没有"，而资产侧用的是另一个键空间；
同一条文章被两个渠道各采一次时，两边都判"新"，重复入列与重复入库都不被挡住。
`short_link_maps.article_key`（`entities.py:157`）是全仓**唯一**一处在用规范键的地方，
它是 STEP-R0 为资产反查加的旁路，不承担清单↔资产对齐。

## 2. 决策

1. `article_manifests` **新增列 `article_key String(128) NOT NULL`**，值 = `canonical_article_key(url)`
   （ADR-0011 的 `b:/s:/h:` 形状）。`external_id` **保留渠道 id 不动**，幂等键
   `uq_manifest_source_external (source_id, external_id)` 也**不变**——它是渠道内翻页依据，
   改成规范键就丢掉"上游给了什么 id"这一事实（D-V3-01 的否决项）。
2. **任何新表引用文章一律用 `article_key`**（D-V3-01）。清单↔资产对齐、Diff 判据、
   后续告警与统计的 join 键都是 `article_key`，渠道 id 不参与跨层匹配。
3. `job_items` 增加 `manifest_id`（FK → `article_manifests.id`），入列与写 job_items
   **同事务**，这样"清单行处于 ENQUEUED"才是可信事实而不是推断。
4. 清单状态机四态（`app/contracts/collection.py::ManifestStatus` 已钉值集）：

   ```
   DISCOVERED → ENQUEUED                     （入列，同事务写 job_items.manifest_id）
   ENQUEUED   → INGESTED                     （worker 终态 SUCCEEDED）
   ENQUEUED   → FAILED                       （永久失败；限流/可重试不算）
   ENQUEUED   → DISCOVERED                   （stale 回退：超 TTL 且无活动 Job）
   FAILED     → DISCOVERED                   （仅人工/重试接口）
   ```
   其余迁移非法，特别是 `INGESTED → ENQUEUED` 与 `FAILED → INGESTED` 必须被拒
   （S1.4.2 的 `events.schema.json#/definitions/ManifestTransition` 已把这两条列为
   `illegalEdgesMustBeRejected`）。

## 3. 不变量（契约/测试锚）

1. 同一 `article_key` 在 `article_manifests` 里**至多一条**处于非终态
   （`DISCOVERED`/`ENQUEUED`），否则"重复入列"仍会发生。唯一约束不加（存量脏数据要先回填），
   由服务层 + STEP-07 审计守住；这条是**有意的妥协**，写清楚而不是装作已解决。
2. `article_manifests.article_key == canonical_article_key(article_manifests.url)`，
   且与 `content_assets.external_id` **同键空间**（这是本 ADR 存在的全部理由）。
3. `job_items.manifest_id` 非空 ⇒ 该清单行状态必为 `ENQUEUED` 或已进入终态；
   反向不成立（stale 回退后 `manifest_id` 仍指向历史作业，那是审计证据）。
4. 状态迁移只能沿 §2.4 的边；每次迁移产一条 `CollectionEvent`（`manifest.enqueued` /
   `manifest.ingested` / `manifest.failed` / `manifest.stale_reverted`），事件名与枚举值集
   由 `tests/test_collection_contract.py` 钉住。

## 4. 迁移与可回滚（D-V2-02 的硬要求）

- 迁移号 **`ab1006c1a`**，当前头是 `ab1005w5b`（`alembic/versions/ab1005w5b_extra_config_encrypt.py:30-31`），
  由 STEP-04 持有；STEP-08 的 `ab1006c2a` 依赖它 ⇒ 两卡串行，不并发占号。
- `upgrade()` 加列 + 加 `manifest_id` + 建索引；**`downgrade()` 必须真能退回**（丢列前先丢依赖它的索引）。
- CI 判据：在 ubuntu 上跑 `upgrade → downgrade → upgrade` 往返，且单头断言不红
  （`.github/workflows/ci.yml` 已有 alembic 单头步）。
- 大表加 `NOT NULL` 列不能裸加：先加可空列、回填、再收紧——顺序属 STEP-07 回填脚本，
  本 ADR 只钉"不许一把 ALTER 上去"。

## 5. 回填归属（不在本卡做）

存量 `content_assets.external_id` 含 `"s"` 与裸 token 两类脏键（ADR-0011 §5），
`article_manifests` 侧回填 `article_key` 由 **STEP-07** 承担，顺序固定为
只读审计 → dry-run → 测试库实跑并验证可回滚 → 备份 → 生产实跑（D-V2-06）。
**回填完成前不得依赖等值 join 做跨号判定**，也不得据本 ADR 的不变量 1 上线任何"自动去重删除"。

## 6. 代价与局限

- 一行清单多一个键列，且 `external_id` 与 `article_key` 长期并存——新人会问"该用哪个"。
  答案固定在 §2.2：**跨层一律 `article_key`**，词表见 `docs/00_governance/glossary.md`。
- 源侧键是第三套：`sources.external_id = biz or _biz_from_profile_url(profile_url)`
  （`app/services/subscription.py:113`，列注释 `entities.py:62` 写「公众号 biz」），
  D-V3-01 明示源侧**不并入**本次统一 ⇒ 全仓长期是三套键并存，本 ADR 只对齐清单↔资产这一层。
- 不变量 1 靠服务层守，不是数据库守：并发入列仍可能在回填前造出两条非终态行，
  这是明知而接受的窗口，STEP-07 回填后可考虑升级为部分唯一索引。

## 7. 验收（全部标机器，主验收机 `@ci` ubuntu-latest）

- [ ] `@ci` 迁移往返：`upgrade → downgrade → upgrade` 成功，alembic 单头断言不红。
- [ ] `@ci` 契约测试：`ManifestStatus` 值集 == 冻结稿 enum；`CollectionEvent.event` 覆盖四条边。
- [ ] `@win`/`@linux` 服务层用例：非法两条边各 1 例断言被拒（STEP-04 S4.4.2.1）。
- [ ] `@ci` 反证：把 `article_key` 从 Diff 判据里摘掉 ⇒ 至少一条用例必须红（否则"对齐"没有测试在看）。
