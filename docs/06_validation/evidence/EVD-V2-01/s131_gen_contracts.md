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
| `ruff check scripts/gen_contracts.py` 从仓库根 | rc=0（**但这个读数没用**：见 §7） |

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

## 7. 独立验证判 PASS，但抓到 4 条 overstatement（都已修）

判定：**S1.3.1 PASS**，产物可以留（它同时否证了我担心的所有权冲突——见 §7.4）。
四条是我的说法比读数强：

### 7.1 `ruff rc=0` 是 **cwd 依赖**的读数，我拿错了口径

`ruff check scripts/gen_contracts.py` 从**仓库根**跑 rc=0；从 **`apps/api`** 跑
（也就是 CI 后端的 cwd）rc=**1**，报 `E501 Line too long (121 > 120) --> scripts\gen_contracts.py:13`。
根因：`pyproject.toml` 的 ruff 配置住在 `apps/api` 下，从那儿跑才吃到 `line-length=120`。
⇒ 我表格里那行 rc=0 是真的，但**它没有证明任何事**，因为门禁不在那个 cwd 上跑。
已把该行缩短并改成"从仓库根 rc=0（但这个读数没用）"。
补一条更大的事实：**CI 根本不 lint `scripts/`**（`ci.yml:68` 是 `ruff check app tests`）
⇒ `scripts/*.py` 全在 lint 面外，这条挂到发布清单 P-7。

### 7.2 "逐字节比较"当时是假的：`read_text()` 让 CRLF 版产物也 rc=0

验证者探针：把产物只改成 CRLF ⇒ `--check` 仍 rc=0。
⇒ 两个 check 函数改成 `read_bytes() != content.encode("utf-8")`，并**重做了反证**：

```
造一份仅换行不同的产物 → check_schemas rc = 1（期望 1）
   [error] …collection.schema.json 与生成结果不一致（非幂等，字节比较）
恢复后字节一致: True
```

### 7.3 换行这件事在本机 worktree 里是真的（诊断过程，别当成噪音）

改成字节比较后 `--check` 从 apps/api 跑 **rc=1**，6 个 dto.ts 全报不一致。诊断：

| 读数 | 结果 |
|---|---|
| `git config --get core.autocrlf` | `true`（用户全局设置，**我没动、也不允许我动**） |
| `git check-attr -a packages/contracts/src/bot/dto.ts` | `text: set`、`eol: lf` |
| `git show :packages/contracts/src/bot/dto.ts` 的行尾 | index/HEAD blob：**LF**（CRLF=0，LF=89） |
| 改前 worktree 的行尾 | 6 个 dto.ts 全是 **CRLF**（bot/dto.ts 89 个 CR） |
| 重跑生成模式后 | worktree CRLF 总数 = 0，`--check` **rc=0**、7 条幂等一致 |
| `git diff --stat -- packages/contracts/src` | **空**（内容与 index 逐字节等） |
| 但 `git status --porcelain packages/contracts` | 6 条 ` M`（`git update-index --refresh` 后仍在） |

⇒ 结论：`core.autocrlf=true` 与 `.gitattributes eol=lf` 在这台机器上打架——git 的 stat 缓存把
"worktree 从 CRLF 变 LF"标成已修改，而内容 diff 是空的。所以这 6 个 ` M` **不是变更**，
我**没有把它们加入暂存区**（`git diff --cached --name-only` 为空），本次提交只含我真正改的文件。
CI 侧按 `.gitattributes` 检出就是 LF，字节比较预期 rc=0；**但这是推断**，
真正的凭据是推送后 `Contract drift gate` 那一步的步级结论（待取，见 §8）。

### 7.4 所有权疑点被否证（我原本担心产物越权）

`packages/contracts/**` 出现在 **00W** 卡的禁止清单里（那是 00W 不许碰契约），
01 卡从来没有这条：来源卡 `:11` 明写 `scripts/gen_contracts.py` 与
`packages/contracts/schemas/collection.schema.json（生成）`为 01 的写所有权，
V0.12.0 卡 `:19` 只禁"他卡所有路径"，`04:98` 把 `packages/contracts/**` 划给 Contract 列。
⇒ 产物合法入库，不需要搬走。

### 7.5 登记表的两处更正 + 两条新增（10 → 12 条）

| 动作 | 内容 |
|---|---|
| **删掉一半的假话** | 原 #3 声称"稿里 `CollectionEvent.event` 也在 `$defs`"——**稿里本来就是内联 enum**（验证者复核），所以它根本不构成差异。已从该条删除，只留 ArticleKey 那一半 |
| 新增 `documentation` 这一 kind | 原来只有四类，覆盖不了"只动人读文本不动校验"的差异 |
| 新增 #11 | def 级 `description`：生成物每个模型都带（来自类 docstring），稿里只有 3 个 def 带 ⇒ 比对脚本剥离文本、只要求"稿里有 ⇒ 生成物也得有" |
| 新增 #12 | 稿的 `ArticleKey.x-not`（注释性禁令）在生成物无对应键 ⇒ 不能一删了之，P0-1 那条回归锚改由见证向量承担，并要求"稿里每个 `x-*` 都必须能在登记表里找到归宿" |

现在 12 条：`structural 5 / tightening 3 / serialization 1 / strictness 1 / documentation 2`。

## 8. 本步待补的读数（写清楚，别让读者以为已经齐了）

- `@ci` 步级：`Contract drift gate (gen_contracts --check)` 在**字节比较版**下的结论——**尚未取**
  （本次推送之前 CI 只跑过字符比较版）。已存的是字符比较版的步级读数
  `ci_drift_gate_6ec473a.md`（run 38731161342 / job 116409001417 / step success）。
- `@ci` 上 `scripts/` 的 lint 面：**不存在**，所以 §7.1 那条 E501 从来没被 CI 抓过，
  是我自己从 apps/api 跑才发现的。
