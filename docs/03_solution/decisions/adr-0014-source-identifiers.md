---
id: ADR-0014
type: decision
title: 信息源标识表 `source_identifiers`（一源多标识）与其两条不变量
status: accepted
owner: architecture
created: 2026-10-21
updated: 2026-10-21
related: [D-V2-04, D-V2-01, ADR-0011, ADR-0012, ADR-0013, STEP-06, STEP-08, STEP-09]
---

# ADR-0014：信息源标识表 `source_identifiers`

本 ADR **不新增决策**：它把台账里的 **D-V2-04**（STEP-08 的裁决锚：一个源可持有多种标识，
渠道按"所需标识 ∩ 源已有标识 ∩ 成本"选择）与 STEP-08 卡面 S8.1.1 的表位写成可实现、可测的形状。
起草由执行方完成（与 ADR-0013 同一先例：本仓规矩是"DDL 必配一支 ADR"，
而卡面只给了"建 source_identifiers + SQL 回填 biz"这一句，没给取舍理由）。
若与台账冲突，以台账为准并回来改本文件。

## 1. 背景与被否证的现状（现读锚）

| 事实 | 锚点 |
|---|---|
| 一个源只有一个标识位 | `app/models/entities.py` 的 `Source`：`external_id`（注释写死"公众号 biz"）+ `url` + `name` |
| 但渠道要的标识**不止 biz** | `providers/article_sources/base.py:74` 明写"Dajiala/JustOneAPI/TikHub：ghid（gh_xxx）"、`wellbyte.py:21` 明写"需要一个文章 URL 作为入口"、RSS 要 feed_url |
| 现在怎么绕过 | 各 provider 的 `query_work_list(identifier, page)` 里**由调用方猜**该传哪种标识：`dajiala.py:85` 注释"identifier = ghid"、`tikhub.py:16`"username=ghid"、`wellbyte.py:121`"入口是 URL" |
| 上游返回里已有 ghid | `dajiala.py:176`、`justoneapi.py:222`、`tikhub.py:222` 都读了 `gh_id`/`ghid`，但**落不进库**（没有列） |

⇒ 缺口不是"少一列"，而是**标识的种类由调用方在代码里各自约定**。加一家渠道就要在调用点重猜一次，
猜错的表现不是报错而是"清单为空"——与本仓反复出现的静默失败同形（P0-1 键坍缩、D23 假链接抓取）。

## 2. 决策

新增**一张**表：

```
source_identifiers(
  id          varchar(36)  PRIMARY KEY,
  source_id   varchar(36)  NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  kind        varchar(16)  NOT NULL,   -- biz | ghid | sample_url | feed_url
  value       varchar(512) NOT NULL,
  origin      varchar(16)  NOT NULL,   -- source | resolver（见 §3 第三条）
  created_at  timestamptz  NOT NULL,
  CONSTRAINT uq_source_identifier_kind_value UNIQUE (kind, value)
)
+ ix_source_identifiers_source_id (source_id)
```

同迁移内做**一次性回填**：把 `sources.external_id` 里非空的值写成 `(kind='biz', origin='source')` 行。
不播种别的种类——ghid 只能从真实解析/映射来，凭空播种就是造假标识。

两条不变量（它们才是本 ADR 的可测部分）：

1. **一个 `(kind, value)` 只属于一个源。** 唯一约束在 DB 侧，不靠应用层查重。
   理由与本仓最贵的一条教训同源：同一篇文章/同一个号主身份落到两个行上，
   表现是"缓存命中但内容是另一篇"（P0-1、D-01b 的 biz/`__biz` 坍缩）。
2. **标识种类是封闭集合，且在应用侧校验。** `kind` 用 `String(16)` 而不是 DB enum
   （AGENTS.md 关键约束 3 的同一口径：加一种标识不该发一次 DDL），
   但 `app/services/identifier_resolver.py` 只认 `IDENTIFIER_KINDS` 里那四种，
   写进未知 kind 的行**读侧一律不认**（宁可少选一个渠道，不要拿猜错的标识去打付费接口）。

## 3. 为什么是这些列（三条取舍）

- **为什么不直接给 `Source` 加三列（`ghid` / `sample_url` / `feed_url`）？**
  列的形状随渠道增长：Wellbyte 的入口是**文章 URL**，而一个源可能有多个这样的 URL；
  RSS 的 feed_url 同理。展平成列等于每加一类标识发一次 DDL，且"多值"那一类根本展不了。
  代价是**没有 DB 侧的列类型保护**：kind 的合法集只能靠应用层，这条由不变量 2 承担。
- **为什么不复用 `Source.url`？** 那一列今天已经承担"样例链接"语义（`sources.py` 建源时写入），
  再拿它当第二种标识的存储位，就是同一列两种含义——本仓在 `sub` 上付过这个学费（P-26：
  同一个 `sub` 在两域两种形状），结果是一个域改了另一个域静默失效。
  本卡**不迁移** `Source.url`（它仍是源自己的属性），只是另外有了一张"这个源还认识哪些标识"的表。
- **为什么要 `origin`？** `S8.2.1` 的"从 biz 补 ghid"是**推导**，推导可能过期或错
  （上游映射变了）。没有 origin，推导来的行与源自己给的行在库里长得一模一样，
  出了问题只能靠猜。`origin ∈ {source, resolver}` 是"这条标识从哪来"的最小可查记录，
  与 ADR-0013 给 `system_settings` 留 `updated_by` 是同一个理由。

## 4. 被否决的方案

- **把 ghid 塞进 `Source.external_id`**：那一列有 `uq_source_type_external` 唯一约束与
  `Source.type` 绑定，改写它等于把源的对外身份换掉——已有清单行、订阅、资产锚全按旧值建，
  这是"改一处、断三链"。
- **不建表，运行时从上游现取 ghid**：每次调度都多打一次上游（付费的），
  且渠道选择的判据变成"能不能现场问到"，问不到就静默不采——比配置错误更难查。
- **JSONB 一列装所有标识**：与 ADR-0013 的 `system_settings` 看起来同形，实则不同判据：
  配置是"整体读、整体写"，标识是"按 (kind,value) **反查源**"。
  反查在 JSONB 上要 GIN 索引 + 表达式路径，代价高于关系表，且拿不到 `(kind,value)` 唯一约束。

## 5. 局限与影响面

- **本表不承担凭据**，也不承担文章级标识（文章规范键在 ADR-0011，落在 `article_manifests.article_key`）。
- **回填是一次性的**：迁移之后再建的新源不会自动获得 biz 行——写源的那条路径
  （`kb._ensure_source` / 订阅导入）不在本卡所有权内，补齐它属于 S8.2 的 resolver 职责；
  本卡的读侧对"没有 biz 行"的源按"没有该标识"处理，不报错也不猜。
  这条是真实缺口，登记在 EVD 里而不是藏起来。
- 影响面：迁移 `ab1006c2a`（`down_revision` 以合入时 `alembic heads` 为准，现读是 `ab1006c4a`）、
  `SourceIdentifier` 实体、`identifier_resolver.py`（新）、`registry.py` 的 `ChannelSpec`（S8.4）、
  `providers/article_sources/base.py` 与 5 个 provider 的签名（S8.3）。
  **必须带真实 `downgrade()`**：CI 的往返步会升 head 再降回来并在 `information_schema` 探列
  （见 `scripts/migration_roundtrip_probe.py` 的 `SHAPES`，新头不登记就直接判红——P-60 修复后的行为）。
- 与 STEP-09 串行占号：本卡持 `ab1006c2a`、09 条件持 `ab1006c3a`，禁止并行。
