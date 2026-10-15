# EVD-V2-01 · STEP-01 采集域契约冻结

本目录随 STEP-01 推进增量填充。当前在位：**S1.2.1**（Pydantic 唯一源 `collection.py`）。

## S1.2.1 读数（@win，2026-10-15，基线 `75abba7`）

命令：`apps/api/.venv/Scripts/python.exe -X utf8`，脚本 `.staging/verify_contracts.py`（scratch，
按纪律不入库；本文件记录其**输出**而非脚本）。

### 1. `ArticleKey` 的 pattern：期望接受与实际校验**逐条一致**（8/8）

| 见证串 | pattern 期望 | 模型校验结果 | 报错类型 |
|---|---|---|---|
| `b:MzI4NjA5NTU4Mg:2650635316:1` | 接受 | 接受 | — |
| `s:abcDEF12` | 接受 | 接受 | — |
| `h:0123456789abcdef0123456789abcdef` | 接受 | 接受 | — |
| `s`（ADR-0011 不变量 1 的退化形状，P0-1 回归锚） | 拒绝 | 拒绝 | `string_too_short` |
| `ssssssss` | 拒绝 | 拒绝 | `string_pattern_mismatch` |
| `b:a:b:c` | 拒绝 | 拒绝 | `string_pattern_mismatch` |
| `h:0123456789ABCDEF0123456789abcdef`（大写 hex） | 拒绝 | 拒绝 | `string_pattern_mismatch` |
| `x:abcdefgh`（未知前缀） | 拒绝 | 拒绝 | `string_pattern_mismatch` |

### 2. 结构性差异与一处收紧（都写在模块 docstring 里，不是藏 diff）

| 项 | 冻结稿 | 本模块生成物 | 性质 |
|---|---|---|---|
| `ArticleKey` | `oneOf` 三条 pattern | 一条带锚 alternation `^(?:A\|B\|C)$` | 等价（三分支前缀互斥），S1.3.2 按见证向量核 |
| 可空 | `"type": ["string","null"]` | `anyOf[..., {"type":"null"}]` | 等价写法 |
| `$defs` | 9 条全在 `$defs` | 枚举进 `$defs`（实测 `ManifestSyncReport` → `$defs: ['ChannelName']`、`ArticleManifest` → `['ManifestStatus']`），约束别名 `ArticleKey` 内联 | 结构差异，语义不变 |
| `publish_time` / `at` | `format: date-time`（**默认只是注记，不校验**） | `AwareDatetime` ⇒ 无时区被拒 | **故意的收紧**（冻结稿自己的说明就是"时间一律 ISO 8601 带时区"）。实测：`"2024-01-01"` → `timezone_aware` 拒；`"2024-01-01T00:00:00+08:00"` → 通过。代价写明：以前过 schema 的无时区 provider 现在被拒 |

### 3. 其余实测读数

- `WorkListRow`：`additionalProperties: true`、`required: ['id','url','title']`；额外字段 `upstream_fld=7`
  被透传保留；`id=""` → `string_too_short`、缺 `id` → `missing`、`url="http:/"`（7 字符）→ 拒。
  **我第一版见证用 `http://x` 误判成"意外通过"**——那串正好 8 字符，是被 min_length 合法放行的，
  错在我的探针不是模型。
- `ManifestSyncReport.required` = 冻结稿的 8 项，`all_skipped_pages` 不在 required（与稿一致，COULD 字段）。
- `CollectionEvent.required = ['event','source_id','channel','at']`，`event` 内联枚举 7 值（与稿一致）。
- `DiscoveryChannelView` 序列化键实测为
  `name, description, implemented, enabled, available, reason, contractVerifiedAt, verifiedScope, lastSuccessAt, lastError`
  ⇒ camelCase alias 生效，与 `app/providers/discovery/registry.py:333-340` 的真实输出同形
  （`lastSuccessAt`/`lastError` 是 STEP-05 的 COULD 新增，现在只是契约占位）。
- 未知渠道 `channel="weixin"` → `enum` 拒。
- **无反向依赖**（S1.2.1.2）：AST 扫 `collection.py` 的 import，结果只有
  `['__future__','enum','pydantic','typing']`；`app.services` / `app.providers` / `app.models` / `app.api`
  出现次数 0。
- 工具门：`ruff check app tests` rc=0；`mypy app` **109 files** rc=0（新增 2 个文件）。

### 4. 卡面与冻结稿的一处命名不一致（不改任何一方，记账）

卡 S1.2.1 要求实现 `DiscoveryReport`，冻结稿里**没有**这个名字；实际对应两个 `$defs`：
`ManifestSyncReport`（单源单轮发现报告）与 `DiscoveryChannelView`（后台渠道就绪度视图）。
本模块按冻结稿命名（唯一源是模型，卡片是任务描述），不新造第三个名字。

### 5. 本步没做的

- 尚未接 `gen_contracts.py` 生成 `packages/contracts/schemas/collection.schema.json`（S1.3.1）；
- 尚未有 `tests/test_collection_contract.py`（S1.4.1）——所以上面的见证向量现在是**脚本读数**，
  还不是 CI 门禁；落测试前它不会自己变红；
- 其余四契约（identity/events/resources/api）未收编（S1.2.2）；
- `ChannelName == registry.CHANNELS.keys()` 已实测相等（本次会话内 6 个键顺序也一致），
  但这条**断言**要等 S1.4.1 才进门禁。
