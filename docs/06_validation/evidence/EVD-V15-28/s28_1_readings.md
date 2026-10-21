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

## 4b. P-60 的后果比预想的硬，且已按用户授权修好（同一批内）

`7c4bda8` 推上去之后 **ubuntu `CI` 与 `CI-Windows` 同时红**（run 39570548947 / 39570548948），
两红的根因是同一条，且都不是我这个迁移本身有错：

| 红处 | 实测根因 |
|---|---|
| `CI` 的 Migration roundtrip 步 | 探针只检 STEP-04 那两列的"消失"；`downgrade -1` 现在落到 `ab1006c1a`，那两列**本来就该还在** ⇒ `--expect=absent` 恒违规 |
| `CI-Windows` 的 Backend tests | `test_manifest_asset_alignment.py:40` 把 `NEW_REV = "ab1006c1a"` 当"新迁移"，断言"恰有一个版本不在自己父链上"；出现更新的头之后是**两个** ⇒ `assert 2 == 1` |

⇒ 这两处合起来的真实语义是"**`ab1006c1a` 永远必须是 head**"，所以 P-60 的后果不是"少检一张表"，
而是**任何后续 DDL 卡都出不了门**（一个恒红）。用户 2026-10-21 授权修这两处（越 STEP-28 允许面）。

修法与判据（都带反证，不靠"改完就绿"）：

- 探针：形状按 **revision 登记**（`SHAPES`），CI 步检的是"**当前 head 自己声明的那一份**"；
  并且 **新头不在 `SHAPES` 里登记就直接判红**（`resolve_shape` 给出一条可操作的点名）。
  这是把"恒红"换成"恒响"——漏登记会出声，而不是谁都动不了。
- 测试：父链判据改为**从版本目录动态推 head**（`head = 不被任何人当作 down_revision 的那一支`），
  同时保留 STEP-04 的原保证（`ab1006c1a` 仍在链上、其父仍是 `ab1005w5b`），泛化不顺手丢历史。
- 新增三发反证用例：合成版本目录上的**分叉 / 错父 / 成环**三态各自被抓；未登记 head ⇒ 探针响；
  假 `downgrade()`（表还在）⇒ absent 侧给 4 条违规而不是绿。

端到端复算（本机 `bothot_test`，与 CI 同三步）：

| 步 | 结果 |
|---|---|
| `alembic downgrade -1` | rc=0 |
| 探针 `--expect=absent` | `revision=ab1006c4a 实得列=[] 索引=[]`，**rc=0** |
| `alembic upgrade head` | rc=0 |
| 探针 `--expect=present` | 四列齐全，**rc=0** |
| `pytest tests/test_manifest_asset_alignment.py tests/test_audit_scripts.py` | **30 passed / 12 skipped**（跳过的是无 DSN 面，本批无新增连库用例 ⇒ `SKIP_BASELINE_WIN` 不动） |
| `ruff check tests app` | rc=0 |

## 5. S28.1.2 及之后的两个设计问题：量出来的事实与已得的裁定

本节最初记的是"没答案所以停"。用户 2026-10-21 已就两条分别裁定，下面把**事实**与**裁定**并排写清，
供实现与下游复核（截至本文件，实现尚未开始）。

1. **读路径是同步且无 DB 会话的。** `categorizer.categorize()`（同步，被 `kb.py:545` 调）、
   `registry._whitelist(settings)` 与 `registry.resolve_default_channel(settings)`（同步、只收 `Settings`），
   而卡面 S28.2.1 要求那两个函数"**签名不变**"。
   ⇒ **裁定：进程内 TTL 快照 + 异步刷新**。同步读函数只读"最后已知快照"（空 = env 兜底），
   scheduler/worker 在每轮开头异步刷一次。这条同时满足"签名不变"与"下一轮生效"，
   代价（最多 TTL 秒的跨进程窗口）已写在 ADR-0013 §5。
2. **契约步原本没有合法实现路径**：卡面要"在 `packages/contracts` 新增 DTO"，那里却是生成物
   （手改在 `gen_contracts --check` 下失败），而唯一真源 `apps/api/app/contracts/**` 与
   新增域所需的 `scripts/gen_contracts.py` 都不在允许面内。
   ⇒ **裁定：放进已映射的 `app.contracts.collection` 域**（`DiscoveryChannelView` 本来就在该模块，
   采集配置与分类同属采集域），因此只扩 `collection.schema.json`、不产出 `src/admin/dto.ts`，
   也不动生成器；随本裁定授权使用 `apps/api/app/contracts/**`。
   卡面写的 `admin/discoveryConfig`、`admin/categoryConfig` 两个名字因此**落在 collection 域内**，
   这一处偏离卡面已在 ADR-0013 与本节留痕。
