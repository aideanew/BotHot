# EVD-V15-28 · S28.1.1 存储底座（迁移 + 模型）执行方读数

> 卡面：`docs/任务规划V0.15.0/steps/STEP-28-采集渠道与分类运营可配置-后端.md`。
> DDL 的形状与取舍在 **ADR-0013**；本文件只记"落地并验了什么"。
> 本文件所属批次只含 S28.1.1（迁移 + 模型），S28.1.2 及之后尚未开始，原因见 §5。

## 1. 迁移往返（S28.1.1.a 要求的读数）

隔离库 `bothot_test`（PG 16.4@5547），`DATABASE_URL` 指向它：

| 步 | 命令 | 读数 |
|---|---|---|
| 单头 | `alembic heads` | `ab1006c4a (head)` —— 只有一个头 |
| 升 | `alembic upgrade head` | rc=0，`Running upgrade ab1006c1a -> ab1006c4a` |
| 降 | `alembic downgrade -1` | rc=0，`Running downgrade ab1006c4a -> ab1006c1a` |
| **低点形状探针** | `information_schema.tables where table_name='system_settings'` | **0**（表真的不在了），`alembic_version = ab1006c1a` |
| 再升 | `alembic upgrade head` | rc=0，探针 = **1**，`alembic_version = ab1006c4a` |

低点那一行是本卡自己加的判据。原因见 §4：**CI 的往返步不会发现"假 downgrade"**，
所以"我写了真的 `downgrade()`"这句话必须由探针证明，不能由"rc=0"证明——
版本号回退与表是否消失是两件事，`alembic_version` 只看前者。

## 2. 落库形状（`information_schema.columns` 实测）

| 列 | 类型 | 可空 | 与卡面/ADR 的对应 |
|---|---|---|---|
| `key` | `character varying`（64） | NO | 主键，约束名 `pk_system_settings` |
| `value` | **`jsonb`** | NO | 本仓库**第一支** jsonb 列（`app/models/**` 与 `alembic/versions/**` 此前 0 命中）；理由见 ADR-0013 §3 |
| `updated_by` | `character varying`（36） | YES | 外键 `fk_system_settings_updated_by_users → users.id`；`users.id` 实测 `String(36)`（`entities.py:22`），类型对齐 |
| `updated_at` | `timestamp with time zone` | NO | `server_default now()`，裸 SQL 与 ORM 两侧一致 |

**不播种**已被读数为事实：`select count(*) from system_settings` = **0**。
这条不是"还没做"，而是本表语义（无行 = 走 env 兜底，删行即回退）。

## 3. 静态面

- `ruff check app`、`mypy app`（115 files）rc=0；新迁移单文件 `ruff check` 亦 0。
- 模型形状与迁移逐列对齐：`python -c "import app.models.bothot_entities as m; …"` 打出
  `VARCHAR(64)/JSONB/VARCHAR(36)/DATETIME(tz)` + `pk=['key']` + `fk updated_by → users.id`。

## 4. 顺手查出的一条门缺口（登记 P-60，不在本卡修）

CI 的 Migration roundtrip 步探的是 `scripts/migration_roundtrip_probe.py` 里**硬编码**的
`COLUMNS = {"article_manifests": "article_key", "job_items": "manifest_id"}`（STEP-04 那两列）。
新头的表/列不在表里 ⇒ 一支 `def downgrade(): pass` 的新迁移照样能让这一步绿：
`alembic downgrade -1` 只回退 `alembic_version`，不校验对象是否消失。
所以"CI 有往返门"这句话的实际覆盖面比它的名字窄。

不在本卡改的理由有两条，都要写清：① STEP-28 的允许面不含 `scripts/migration_roundtrip_probe.py`；
② 那支探针还有"两个集合都只认列与索引名"的形状，加一支**新表**需要判据形状先定
（表存在性 vs 列存在性是两件事）。P-60 里给的就是这个待定项。

另记一条同类观察：`ruff check alembic` 会报既有迁移 `ab1004w1a_secret_aes.py:13` 的 `I001`
（import 未排序），而 CI 的 lint 面是 `ruff check app tests` ⇒ 长期无人看见。
`alembic/**` 对本卡是"仅新增文件"的禁改面，故只登记不顺手修。

## 5. 本批为何停在 S28.1.1（不是漏做，是两个设计问题没答案）

量出来的两条事实，决定了 S28.2/S28.3 的接法不能照卡面直接写：

1. **读路径是同步且无 DB 会话的。** `categorizer.categorize()`（同步，被 `kb.py:545` 调）、
   `registry._whitelist(settings)` 与 `registry.resolve_default_channel(settings)`（同步、只收 `Settings`）。
   卡面同时要求 registry 那两个函数"**签名不变**"。⇒ "库值优先"只能是
   **进程内 TTL 快照 + 一个异步刷新者**（scheduler/worker 各自维护），不能把 session 注进同步读路径。
   这与 ADR-0013 §5 写的"跨进程一致靠 TTL 不靠广播"是同一条，但卡面没写快照层的形状。
2. **契约步没有合法实现路径。** 卡面 §2 要"在 `packages/contracts` 新增 DTO"，允许面列的是
   `packages/contracts/src/**`（**生成物**，手改会在 `gen_contracts --check` 下失败）；
   而唯一真源 `apps/api/app/contracts/**` 与新增域所需的 `scripts/gen_contracts.py`
   （`CONTRACT_SCHEMAS` 是一张固定映射表）**都不在允许面内**。
   ⇒ 三个候选：把新 DTO 放进已映射的 `app.contracts.collection`（`DiscoveryChannelView` 本来就在里面，
   但它只扩 `collection.schema.json`，不产出 `src/admin/dto.ts`）／授权我扩生成器开 `admin` 域／
   把契约步从本卡剥出交规划方。这条需要裁定，不自行选。
