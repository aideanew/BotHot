# S1.3.1 读数和反证（@win，基线 `abd55a0`）

让 `scripts/gen_contracts.py` 从 `apps/api/app/contracts/*.py` 生成
`packages/contracts/schemas/collection.schema.json`，并纳入 `--check` 幂等门禁（ADR-0008 的产物面）。

## 1. 改法是**加法**，TS 面逐字节没动

这点必须先证，因为 CI 的 backend job 有一步就是 `gen_contracts.py --check`
（`.github/workflows/ci.yml:97-98`），动到 dto.ts 的字节 = 直接碰红门禁。

| 读数 | 结果 |
|---|---|
| `cd apps/api && .venv/.../python -X utf8 ../../scripts/gen_contracts.py --check` | **rc=0**，输出 7 行"幂等一致"（6 个 dto.ts + 1 个 schema） |
| `git status --porcelain packages/contracts` | 只有 `?? packages/contracts/schemas/`，**没有任何 `M .../src/**/dto.ts`** |
| `ruff check scripts/gen_contracts.py` | rc=0 |

实现要点（都是"少一个将来会咬人的坑"）：
- `$defs` 键**冲突就抛**（同名不同体 ⇒ `SystemExit`），不静默覆盖；
- `json.dumps(..., sort_keys=True)`：键序稳定，而 **list 不被排序** ⇒ `enum` 与 `required` 的顺序
  仍由模型定义顺序决定（那是要与冻结稿比的东西，不能被归一化掉）；
- `main()` 里两面判定写成 `(check(ts)) | (check_schemas(s))` 而**不是** `or`——
  `or` 会在第一面已失败时短路，第二面的差异一条也打不出来，"门禁只报一半问题"比不报更糟；
- 新增 `--only-schemas`（本地调试面），CI 命令不变。

## 2. 判据与反证

- **S1.3.1.1** `--check` rc=0：见上表。
- **S1.3.1.2** 反证：把生成物里 `WorkListRow.required` 手工篡改成 `["id","title"]` ⇒
  `--check` **rc=1**，报 `[error] packages\contracts\schemas\collection.schema.json 与生成结果不一致（非幂等）`；
  重跑生成模式恢复后再 `--check` rc=0。**漂移门禁确实能抓到"有人直接编辑产物"这条路。**

## 3. 生成物本身的形状（8 个 `$defs`，稿里 9 个）

```
顶层键: ['$defs', '$id', '$schema', 'description', 'title', 'x-generated-by', 'x-source-module']
$defs(8): ArticleManifest, ChannelName, CollectionEvent, DiscoveryChannelView,
          ManifestStatus, ManifestSyncReport, WorkListPage, WorkListRow
WorkListPage.required: ['rows', 'next_cursor', 'page_size']        # 与稿一致（S1.2.1 修的那条）
WorkListRow.properties.url: {"format":"uri","maxLength":512,"minLength":8,"title":"Url","type":"string"}
```

少的那一个正是 **`ArticleKey`**——它是约束类型别名，Pydantic 不为别名建 `$defs`、
在使用处内联展开。这**不是新发现的差异**：它已经登记在
`app/contracts/collection.py::CONTRACT_DIVERGENCES` 第 3 条（structural）。
生成产物自己把登记表说过的话兑现了一遍，这类"产物即证据"的对照是我在这个卡里想要的形态。

`$id` 用 `bothot://contracts/collection/v1`，与稿的 `$id` 同形；另加
`x-generated-by` / `x-source-module` 两个键做溯源（稿里没有 ⇒ 比对脚本必须把它们当生成器附注忽略，
这条留给 S1.3.2 登记，不在这里偷偷归一化）。

## 4. 顺带查出来的一个既有 cwd 敏感（**不是我引入的**，但影响我上一步的一个分支）

从仓库根跑 `--check` 时输出里出现两次：

```
CommandError: Path doesn't exist:  alembic.  Please use the 'init' command to create a new scripts folder.
```

根因实测（同一解释器，只换 cwd）：

```
cwd=仓库根   → schema_guard.get_alembic_head() = None
cwd=apps/api → schema_guard.get_alembic_head() = 'ab1005w5b'
```

`alembic.ini` 的 `script_location` 是相对路径 ⇒ **凡是 import `app.main` 的东西都依赖 cwd**
（`generate()` 里 `from app.main import create_app` 早就如此，所以这是既有行为，不是本次加 schema 面带来的）。
CI 不受影响：backend job 的 `defaults.run.working-directory: apps/api`（`ci.yml:27`），
从 apps/api 跑时 CommandError 计数为 **0**。

但它和我 S1.2.1 加的 `_alembic_head()` 前置 skip 有直接关系：那条 skip 的判据就是
`get_alembic_head() is None`。⇒ 在**非 `apps/api` cwd** 下它会让 `test_startup_probe_timeout.py`
**skip 而不是跑**。现实里 pytest 从 `apps/api` 起（`testpaths=["tests"]`，rootdir 也在那），
所以不改变现有行为；但这个耦合必须写在这里，否则下一个人会把它当成随机 skip。

## 5. 本步没做的

- **语义比对**（生成物 vs 冻结稿，逐字段 required/enum/pattern/可空性 + 登记表放行）是 **S1.3.2**，
  现在还没有，所以 `--check` 只保证"产物与模型一致"，**不保证"模型与稿一致"**；
- `tests/test_collection_contract.py`（S1.4.1）未落 ⇒ 键不变量等仍未进门禁；
- 其余四个契约模块（S1.2.2）未收编，`CONTRACT_SCHEMA_MODULES` 目前只有 `collection` 一项；
- 前端 `packages/contracts` 的 `tsconfig.json` 只 include `src/**/*.ts`（实测），
  所以新增 `schemas/` 目录对 tsc 无影响 ⇒ frontend job 不会被这一步碰红（这是**事前**查的，不是出了再补）。
