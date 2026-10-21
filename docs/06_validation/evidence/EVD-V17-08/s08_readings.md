# EVD-V17-08 · STEP-08 执行方读数

> 卡面：`docs/任务规划V0.7.0/steps/STEP-08-信息源标识与按源路由.md`（V0.13.0 起的继承卡只改基线，
> 三级任务沿用来源卡）。DDL 的形状与取舍在 **ADR-0014**。
> 卡面字段 11 写的证据目录 `docs/任务规划V0.8.0/evidence/61358c3-08/` 本仓从未建过
> （与 P-58 同一形状：继承卡在七个版本里逐字复制那一格）⇒ 按现行约定落在本目录，偏离已在 P-65 登记。

## 1. S8.1.1 迁移往返 + 回填（真库演练，`bothot_test`@5547 / PG 16.4）

| 步 | 命令 | 读数 |
|---|---|---|
| 单头 | `alembic heads` | `ab1006c2a (head)` —— 只有一个头 |
| 升 | `alembic upgrade head` | rc=0，`Running upgrade ab1006c4a -> ab1006c2a` |
| 高点探针 | `scripts/migration_roundtrip_probe.py --expect=present` | 六列齐全 + 三索引齐全，rc=0：`ix_source_identifiers_kind` / `ix_source_identifiers_source_id` / `uq_source_identifier_kind_value` |
| 降 | `alembic downgrade -1` | rc=0 |
| 低点探针 | `information_schema.tables where table_name='source_identifiers'` | **表不存在**（`0`）——真 `downgrade()`，不是只回退 `alembic_version` |
| 再升 | `alembic upgrade head` | rc=0 |

### 1b. 回填的"读数 = 播种数"

演练刻意在**降级之后**播种，再升级，才能证明回填属于这次迁移而不是历史残留：

```
播种 sources 4 行：external_id 分别 BIZ-AAA / BIZ-BBB / BIZ-CCC / 空串
低点（表不存在）: (0, '表不存在', [])
升级后:            (1, 3, [('biz', 'source', 3)])
清场后:            (1, 0, [])
```

⇒ 回填 3 条 = 非空 `external_id` 的播种数，**空串那条没有生成行**（判据是"非空才回填"，
不是"每源一行"）；`kind/origin` 全是 `('biz','source')`，与 ADR-0014 §3 第三条一致
（`origin` 要能区分"源自己给的"与 S8.2 resolver 推导的）。

## 2. 形状三方对账（实体 ↔ 迁移 ↔ 探针）

`tests/test_source_identifiers.py` 把三份东西钉在一起，全是**读磁盘/读元数据**，不抄表：

| 判据 | 形状 |
|---|---|
| 列集合 | `SourceIdentifier.__table__` == 迁移里 `create_table` 的 `sa.Column` 名（AST 取） == `SHAPES["ab1006c2a"].columns` |
| 唯一约束名 | `uq_source_identifier_kind_value` 必须同时出现在迁移与 `SHAPES.indexes`（只有一边有 = 探一个不存在的东西） |
| 链序 | 迁移的 `down_revision` == `ab1006c4a`（**不是**卡面当年写的 `ab1006c1a`；STEP-28 字段 9 明文"以合入时 heads 为准"） |

## 3. DB 侧不变量（连库）

| 用例 | 判的是什么 |
|---|---|
| `test_same_kind_and_value_belongs_to_one_source_only` | 不变量 1：同 `(kind,value)` 属于第二个源 ⇒ `IntegrityError`（应用层查重挡不住并发写） |
| `test_the_same_value_under_a_different_kind_is_a_different_fact` | 唯一性是"同一种标识内"的：biz 与 ghid 同值必须允许，否则一个号主的两种标识互相挤掉 |
| `test_deleting_the_source_takes_its_identifiers` | `ON DELETE CASCADE` 真的在：源删掉后按 `source_id` 查得空集（留孤儿 = 反查命中不存在的源） |

## 4. 契约面（卡面 S8.1.1"实体与 dto 同提交生成"）

`scripts/gen_contracts.py` 的 `DOMAIN_ENTITIES["subscription"]` 加 `SourceIdentifier` ⇒
`packages/contracts/src/subscription/dto.ts` 多出该 interface，并在 `src/index.ts` 导出。
`gen_contracts --check` 12 项幂等一致。
越界声明：`scripts/gen_contracts.py` 与 `src/index.ts` 不在继承卡的"所有权（写）"清单里
（那份清单是 V0.7.0 的，只列到 `services/manifest.py`），但同一行的"实体与 dto 同提交生成"
只能靠它们落地 ⇒ 记进 §6。

## 5. 静态面

`ruff check app tests` rc=0；`mypy app`（116 files）rc=0；
`scripts/` 面另有 7 条**既有**告警（`check_docs_consistency.py` 的 W293/B007、
`check_entry_parity.py` 的 E741×2、`entry.py`/`guards.py` 的 E501×2 等）——
CI 的 lint 面是 `ruff check app tests`，看不到它们；本卡未触碰那些文件，只登记不顺手修。

## 6. 越界声明与后续分片

| 越界 | 为什么必须 |
|---|---|
| `docs/03_solution/decisions/adr-0014-source-identifiers.md`（新）与 `adr-index.md` 一行 | 卡面字段 13"迁移目录需 DDL 停转 ADR"⇒ 不动 ADR 就动不了 `alembic/**`；先例是 ADR-0013（同一队列、同一授权形状） |
| `scripts/migration_roundtrip_probe.py` 的 `SHAPES` 新登记 | P-60 修复后，**新头不登记 CI 往返步直接判红**——这不是可选动作 |
| `scripts/gen_contracts.py` + `packages/contracts/src/index.ts` | §4 |

- S8.2（`identifier_resolver.py`）、S8.3（协议升级 + 翻页）、S8.4（按源路由 + 降级开关）、
  S8.5.1（👤 TikHub openapi 核实）各自成一片，读数续写本文件。
- 本卡未做也不该在本卡做：给新写入的源自动补 biz 行（写源路径 `kb._ensure_source` 不在本卡所有权内，
  缺口的表现与后果写在 ADR-0014 §5）。
