---
id: ADR-0013
type: decision
title: 运营可配置项的存储形状（system_settings 单表 KV + JSONB）
status: accepted
owner: architecture
created: 2026-10-21
updated: 2026-10-21
related: [D-V12-12, D-V12-13, ADR-0011, ADR-0012, STEP-25, STEP-28, STEP-14b]
---

# ADR-0013：运营可配置项的存储形状

本 ADR **不新增决策**：它把已签入台账的 **D-V12-12**（运营可配置采集渠道与采集分类；删除渠道与改渠道凭据只给管理员）
与 STEP-28 卡面字段 9（迁移号 `ab1006c4a`、表形状）写成可实现、可测的形状与不变量。
若与台账冲突，以台账为准并回来改本文件。起草由执行方完成（用户 2026-10-21 授权），
因为本仓库前例是"DDL 必配一支 ADR"（`ab1006c1a` 配 ADR-0011、清单↔资产对齐配 ADR-0012），
而卡面只给了列清单、没给取舍理由。

## 1. 背景与被否证的现状（实测锚，main@1f0893d 现读）

| 要配的东西 | 今天只能怎么改 | 锚点 |
|---|---|---|
| 启用哪些发现渠道 | 改环境变量 `discovery_channels` 并重启 | `app/core/config.py:177`、`app/providers/discovery/registry.py:257`（`_whitelist()` 只读 `settings`） |
| 默认渠道 | 同上（`discovery_default_channel`，默认 redfox） | `config.py:180`、`registry.py:280-290` |
| 分类清单与每类关键词 | **改代码发版** | `app/services/categorizer.py:12` `CATEGORIES` 与 `_RULES`；`spaces.py:43` `CATEGORY_ALLOWLIST = frozenset(CATEGORIES) \| {""}` |
| 写接口 | **全仓没有** | `admin.py:476` 只有 `GET /discovery/channels`（只读就绪度） |

两处与卡面文字的偏差在此登记，以免下游照卡面 grep 落空：卡面写的函数名是 `_enabled_set`，
**实际叫 `_whitelist`**；卡面写的行号 `admin.py:467` 已漂到 **476**。

## 2. 决策

新增**一张**表，形状照卡面，且是**只建形状、不播种**：

```
system_settings(
  key         varchar(64)  PRIMARY KEY,
  value       jsonb        NOT NULL,
  updated_by  varchar(36)  NULL REFERENCES users(id),
  updated_at  timestamptz  NOT NULL
)
```

配套的三条不变量（它们才是本 ADR 的可测部分）：

1. **无行 = 走环境变量兜底，行为与改前逐字一致。** 这条是"可回退"的定义：删掉这一行，系统必须回到今天的行为，
   而不是回到另一个默认值。判据形如"复用现有 registry / categorizer / spaces 用例，0 修改通过"。
2. **凭据永不进这张表。** `value` 里出现 `key`/`token`/`secret` 形状即为实现缺陷；写接口用 `extra="forbid"` 拒收，
   读接口不回显。理由见 D-V12-12 的边界（运营配的永远是"用哪家"，不是"用哪家的钥匙"）
   与 D-V12-13（未来供应商可配同样只配"用哪家"）。
3. **生效语义是"下一轮"，不是"立刻"。** 读侧进程内缓存 TTL ≤ 60s。见 §5 的局限。

## 3. 为什么是这个形状（三条取舍）

- **为什么不"一类配置一张表 / 一列"？** 三类配置（渠道、分类、未来引擎选择）的形状彼此不同：
  渠道是 `{enabled[], default}`，分类是**有序** `[{name, keywords[], enabled}]`。
  展平成列意味着每加一种配置就要发一次 DDL；而配置项的变更频率属于运营，不属于发版节奏。
  代价是**类型安全从 DB 侧移到应用侧**：必须有 key 白名单与各自 pydantic 模型在 `system_settings.py` 里把关，
  否则这张表会在两周内变成垃圾抽屉。这条是本决策的承重墙，不是脚注。
- **为什么 `value` 用 `jsonb` 而不是本仓库既有的 `Text`？** 实测：`jsonb` 在 `app/models/**` 与
  `alembic/versions/**` 里**此前一次都没用过**，最接近的先例是 `bot_channels.extra_config: Mapped[str] = Text`。
  那列是 `Text` 有它自己的理由——它存的是**加密后的字节**，DB 侧本来就不该解析它（ADR 之外的既有裁决）。
  配置值不是密文，用 `jsonb` 换来两样东西：写进去即被 DB 验一遍 JSON 合法性，以及
  出问题时可以 `select jsonb_typeof(value)` / 按路径查，而不是把整列捞进 Python 再解析。
- **为什么 `updated_by` 可空并且是 `users.id` 的外键？** `users.id` 实测是 `String(36)`（`entities.py:22`），
  所以 `varchar(36)` 类型对得上。可空表达的是"这行不是人写的"（未来若加播种/迁移写入），
  而不是"审计字段可以忘填"。带外键是因为本仓库在"操作者锚点"上付过学费
  （P-26：同一个 `sub` 在两域有两种形状；STEP-31 的审计负载固定 9 字段也为此而存在）。

## 4. 被否决的方案

- **写 `.env` 文件**：backend / scheduler / worker 是**不同进程**，改文件不会让它们同步；无审计；容器内通常只读。
- **每进程启动时读一次库**：改完要重启才生效，等于把"运营可配"重新变回"发版可配"。
- **把渠道 API key 也做成可配**：越过 D-V12-12 的授权边界，且需要给 `system_settings` 再加一层加密——
  那会把本表从"配置"变成"第二份凭据库"，与 `extra_config` 的加密路径重复。
- **回写历史分类数据**：`content_assets.category` 存的是改名前的旧值。本卡**不回写**；
  接口禁止删除仍被引用的分类（返回 `request_invalid` 并给引用数），只允许新增、改关键词、调顺序、停用。
  停用的含义是"不再新分进来"，历史行与筛选可见性不变。

## 5. 局限与影响面

- **TTL 缓存不是广播。** 改了配置后，最多 60s 内不同进程可能各持旧值；"下一轮调度按新配置跑"这句话
  只对 scheduler 成立，对刚好卡在窗口里的 worker 不成立。若将来要求跨进程立即一致，
  应复用既有 Redis pub/sub（站内通知那条链已经用它），而不是往这张表上加锁。
- **本表不承担凭据，也不承担开关之外的业务数据。** 任何"顺手把某个业务字段塞进配置表"都越界。
- 影响面：迁移 `ab1006c4a`（`down_revision` 以合入时 `alembic heads` 单头为准，现读是 `ab1006c1a`），
  **必须带真实 `downgrade()`**——CI 会往返 head 并探 `information_schema`（见 `EVD-V14-*` 的往返门）；
  新增 `SystemSetting` 模型、`app/services/system_settings.py`、三个写端点与 `packages/contracts` 的新 DTO（只新增不改既有）。
- 与 STEP-08 / STEP-09 串行占号：08 持 `ab1006c2a`、09 条件持 `ab1006c3a`，本卡持 `ab1006c4a`。
