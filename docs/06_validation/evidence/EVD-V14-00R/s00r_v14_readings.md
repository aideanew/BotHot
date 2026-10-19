# EVD-V14-00R · S00R.V14.1 用例密封（main@7d999db · 2026-10-19）

卡面：`docs/任务规划V0.14.0/steps/STEP-继承卡增量-00T-00R-15b-10-05-08-17-14a.md` §B
来源：F-V14-03 / D-V11-06；原卡 `docs/任务规划V0.13.0/steps/STEP-00R-*.md` 的「允许/禁止修改」不变。
允许修改：`apps/api/tests/test_security_middleware.py`（仅此一个文件）。禁止改 `app/core/config.py`。

## 1. 改前红（复现规划方读数，不引用原文）

```
$ cd apps/api && PUSH_SECRET_MASTER_KEY=randvalue-for-repro-8f3a1c \
    ./.venv/Scripts/python.exe -X utf8 -m pytest tests/test_security_middleware.py \
    -q -k "production_guard"
FAILED tests/test_security_middleware.py::test_production_guard_still_reports_all_eight_items
E   AssertionError: assert 7 == 8
1 failed, 15 passed, 49 deselected in 8.58s
```

根因（现读 `app/core/config.py:236-255`）：`production_guard_violations()` 判的是
`Settings` 的 8 个**字段值**，而 `Settings` 是 `BaseSettings`——宿主 env 里只要给出
`PUSH_SECRET_MASTER_KEY` 非空，`if not self.push_secret_master_key` 这一支就不计数，
于是「守卫报 8 项」这条断言读到 7 项。用例读的是宿主环境，不是被测行为。

CI 不设这个变量 ⇒ CI 绿、本机假红。这正是 04 §8 新加"行为类卡附真库探针复跑"的同族问题：
**"绿"的来源必须能指认**（D-V11-06 据此否决了"在 CI 里固定环境"的方案 B）。

## 2. 改后绿（两个方向都测）

| 环境 | 命令 | 读数 |
|---|---|---|
| 敌意（5 个守卫键被宿主设值） | `PUSH_SECRET_MASTER_KEY=… OIDC_CLIENT_SECRET=leaked QA_FIXTURE_TOKEN_PREFIX=leaked ENGINE_KEY_MASTER_KEY=leaked2 SESSION_COOKIE_SECURE=true SESSION_STORE_BACKEND=memory pytest tests/test_security_middleware.py -q` | **70 passed** |
| 干净对照 | 同上但 `env -u` 掉这 6 个键 | **70 passed** in 36.18s |
| 收集数 | `pytest tests/test_security_middleware.py -q --collect-only` | **70 tests collected**（旧文件同命令 65） |
| ruff | `./.venv/Scripts/ruff.exe check tests/test_security_middleware.py` | All checks passed! |

用例数（`.staging/count_cases.py` AST 数 `def test_`，不 grep）：**47 → 52，净增 +5**；
pytest 收集数 **65 → 70，净增 +5**（两个口径同向，参数化展开数未变）。
净增 ≥1 ⇒ 满足 S00T.V14.2 耦合门自身的判据。

> 订正：本节首稿写的是"66 → 69（净增 3）"，两处数字都是凭记忆填的，被首轮独立评现实跑
> 推翻（其读数为旧文件收集 65）。这是本会话第二次"手填数字"，已把"任何计数必须先跑脚本"
> 写进 §4b 与执行记录；现稿的两个口径都由脚本产生。

## 3. 改动内容（为什么是这个形状）

1. `_GUARD_ENV_KEYS`（8 个 env 名）+ 非 autouse 夹具 `sealed_guard_env`：`monkeypatch.delenv(name, raising=False)`。
   - 不做 autouse：本文件其余 60+ 条用例走 `get_settings()`（进程内缓存），把它们全部推入"清空 8 键"
     的状态会改变 `_client()` 首次装配看到的配置——超出本增量"读生产守卫的用例"的范围，代价不可估。
2. 三条读守卫的用例（`blocks_non_whitelisted_env_names` / `whitelists_known_dev_envs` /
   `still_reports_all_eight_items`）显式请求该夹具。第二条当前逻辑上不受 env 影响（白名单先短路返回 `[]`），
   仍然密封：判据是"读守卫"而不是"此刻敏感"，将来白名单判定挪到逐项检查之后就靠这条兜住。
3. `test_guard_env_seal_covers_the_guard_own_item_set`（防复发）：密封清单与守卫**自己的输出**双向对齐。
   三个漂移方向都红——守卫加了第 9 项而清单没跟上；清单漏了一个守卫仍报的键；清单里有个键已不再是判据。
   判据取行为（`len(named)` vs `len(violations)`）而非源码文本扫描：文案改动不影响，改判据才影响。
4. `test_structure_every_guard_reading_test_is_sealed` + 三个纯函数（`_test_funcs`/`_reads_guard`/`_is_sealed`）
   + `test_structure_guard_reading_seal_check_has_polarity`（六种写法正反两侧）+
   `test_structure_seal_fixture_dels_every_guard_key`（夹具循环必须遍历清单本身、只有一次
   `delenv(变量)`、且带 `raising=False`）。
5. `test_guard_key_matcher_rejects_truncated_names`：整词匹配（`(?<![A-Z0-9_])…(?![A-Z0-9_])`）的
   反证——清单写成截断名时"命中"必须失效。

## 4b. 首轮独立评审的 5 条漏检与本轮返工（原文保留）

评审者（general-purpose 子智能体，21 次调用）对本增量给出 C/F 两条 FAIL，其余 PASS。
逐条复算后全部成立，已修：

| # | 缺陷 | 评审实测 | 修法 | 复算 |
|---|---|---|---|---|
| 1 | 扫描只走 `tree.body` 且只认 `FunctionDef` ⇒ 类内用例、`async def` 整体漏检 | `SCAN async-def -> []`、`SCAN class-based-unsealed -> []`；且本仓确有类内写法（`tests/test_wb_push_hardening.py:346` 读同一个守卫） | 新增 `_test_funcs()`：`ast.walk` + `FunctionDef \| AsyncFunctionDef` | `_POLARITY_CASES` 里 async/类内两例现在被扫出 |
| 2 | 只认"属性调用"⇒ `getattr(x, "…")` 与别名 `f = x.…; f()` 漏检 | `SCAN getattr -> []`、`SCAN alias-var -> []` | `_reads_guard()` 认 Attribute 节点 + Call 实参位上的同名字符串 | 同上两种写法各有一例 |
| 3 | 清单命中用子串匹配 ⇒ 截断名（`PUSH_SECRET_MASTER`）双向都绿而夹具清不掉真键（**假绿**） | `T2 truncated key: len(named)= 8 len(kt)= 8 => test still GREEN? True` | `_mentions_guard_key()` 改整词匹配 + 专用反证用例 | §3-5 |
| 4 | 夹具扫描用 `next()`，改名时抛 `StopIteration` 而非断言失败 | 报告级 | 改为"先收集再断言个数==1" | §3-4 |
| 5 | 评审同时指出 `usefixtures` 写法会被我的第一版判据误判为未密封（假红方向） | `SCAN usefixtures-only -> ['test_j 的参数=[]']` | `_is_sealed()` 同时承认形参与 `usefixtures("sealed_guard_env")` | `_POLARITY_CASES` 第 6 例 |

评审还确认了两条我原本写对的方向：`_arg_names` 不取 `vararg/kwarg` 只会造成假红（pytest 不经
`**kwargs` 注入夹具），以及第 9 项漂移确实红在 `len(named) != len(violations)` 那一行。

## 3. 改动内容（为什么是这个形状）

1. `_GUARD_ENV_KEYS`（8 个 env 名）+ 非 autouse 夹具 `sealed_guard_env`：`monkeypatch.delenv(name, raising=False)`。
   - 不做 autouse：本文件其余 60+ 条用例走 `get_settings()`（进程内缓存），把它们全部推入"清空 8 键"
     的状态会改变 `_client()` 首次装配看到的配置——超出本增量"读生产守卫的用例"的范围，代价不可估。
2. 三条读守卫的用例（`blocks_non_whitelisted_env_names` / `whitelists_known_dev_envs` /
   `still_reports_all_eight_items`）显式请求该夹具。第二条当前逻辑上不受 env 影响（白名单先短路返回 `[]`），
   仍然密封：判据是"读守卫"而不是"此刻敏感"，将来白名单判定挪到逐项检查之后就靠这条兜住。
3. `test_guard_env_seal_covers_the_guard_own_item_set`（防复发）：密封清单与守卫**自己的输出**双向对齐。
   三个漂移方向都红——守卫加了第 9 项而清单没跟上；清单漏了一个守卫仍报的键；清单里有个键已不再是判据。
   判据取行为（`len(named)` vs `len(violations)`）而非源码文本扫描：文案改动不影响，改判据才影响。
4. `test_structure_every_guard_reading_test_is_sealed` + `_unsealed_guard_readers()`（AST 纯函数）+
   `test_structure_guard_reading_seal_check_has_polarity`（合成源喂正反两例）。

## 4. 反证与"我的判据自己抓到我的错"（两条，必须留原文）

- 第一版结构判据写的是 `fn.argnames` ⇒ `AttributeError: 'FunctionDef' object has no attribute 'argnames'`。
  改成 `fn.args.argnames` 后**仍然红**：`AttributeError: 'arguments' object has no attribute 'argnames'`
  ——本机解释器的 `ast.arguments` 没注册 `argnames` 属性（该属性在 CPython 里是后挂的便利属性，
  不是字段）。终版用 `posonlyargs + args + kwonlyargs` 显式取名字。**教训**：`argnames` 不可依赖，
  跨解释器要用手得上来的字段。
- 这两次红都是**同一批新增的反证用例**抓出来的：若只写"真文件 == []"那一条，笔误会让它永远绿
  （空守卫）。本轮把 `…has_polarity` 写成正反两例（已密封⇒[]、未密封⇒点名 1 条），
  正是 STEP-20 返工（§24 空守卫）那条教训的复用。

## 5. 前提 / 局限 / 未验证

- 前提：守卫判据仍只读这 8 个字段。若将来 `production_guard_violations()` 改为直查 `os.environ`，
  密封清单要跟着改（§3-3 的用例只保证"字段清单"与"env 名清单"对齐，不保证与其它读取路径对齐）。
- 已知边界（都是**刻意的**，写在这里以免被当成"判据万能"）：
  1. `_reads_guard` 不把 docstring/注释里提到的名字算作读者——否则本文件的自述用例会被自己判红。
     代价：一条只在文档字符串里提名字、实际用别的方式读守卫的用例可以绕过。目前未发现第三种读取写法。
  2. `app_env` 不在密封清单里：它是"闸门"而不是判据字段，且全部密封用例都以 `app_env=` 显式传参。
     若将来有用例不传 `app_env` 而靠宿主 `APP_ENV`，清 8 个键救不了它——这条由
     `test_production_guard_blocks_non_whitelisted_env_names` 的显式传参约束，不是由密封夹具约束。
  3. 只密封本文件（卡面「允许修改」也只有这一个文件）。全库 `Settings(...)` 构造点的普查属 00R 原 9 项。
     旁证：`tests/test_auth.py`、`tests/test_wb_push_hardening.py` 用 kwargs 显式补字段，逻辑上免疫；
     `test_production_config_guard.py` 敌意跑 13 passed（首轮评审代测，本轮未重复）。
- 未验证：CI-Windows 与 CI-Linux 上这 5 条新用例的读数。本机无 Windows，按 `docs/04_engineering/conventions.md`
  §4.3 第 3 条记"待 @ci 复跑"，不写成通过。
- 未改动：`app/core/config.py`、任何生产代码、任何其它测试文件（`git diff --name-only` 复核，含并行会话
  脏文件不计入本增量）。
