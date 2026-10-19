# EVD-V14-25 · STEP-25 角色门单参数化 + 运营写权按 D-V12-12 落地

执行者：规划方（Hark），2026-10-19，基于 main@8cd0e68，与 STEP-24 同一交付提交。环境同 EVD-V14-24。

## 卡面增量（执行前按用户裁决调整，不是执行中放宽）
原卡写"10 个端点全部改 operator"。用户裁决 **D-V12-12**（2026-10-19）收窄为：
| 端点 | 改前（实际） | 改后 |
|---|---|---|
| `POST /bots/tasks` 建任务 | admin | **operator** |
| `PUT /bots/tasks/{id}` 改任务 | admin | **operator** |
| `DELETE /bots/tasks/{id}` 删任务 | admin | **operator** |
| `POST /bots/tasks/{id}/run` 立即执行 | admin | **operator** |
| `POST /bots/{id}/test` 测试推送 | admin | **operator** |
| `PUT /bots/{id}` 改渠道 | admin | **operator 可改名称/启停；`webhook_url`/`secret`/`extra_config` 仅 admin，夹带即整单 10004，且先授权后查库** |
| `POST /bots` 新建渠道 | admin | **admin**（新建即写入凭据，按"改渠道凭据只给管理员"同口径；规划方解释，登记 D-V12-18） |
| `DELETE /bots/{id}` 删渠道 | admin | **admin** |
| `POST /hot/topics/cluster` | admin | **operator** |
| `POST /hot/daily/generate` | admin | **operator** |

## 先红（`s25_red.txt`）
- 结构守卫：`app/**` 共 38 处 `require_roles` 调用，不合规 **10 处**（bots 8 + hot 2），与卡面预期逐行一致。
- 秩矩阵：operator 列 **8 格全 403/10004**；admin-only 面（5 行）与夹带用例改前已经是 admin-only，所以本来就绿——它们锁的是"改后不许放宽"。
- 判据自检：合成源码 5 种违规形态（多参数、空参、变量、星号展开、关键字）全部被点名。

## 修复
- `roles.py`：`_required_rank` 对 `len(roles) > 1` 抛 `ValueError`；docstring 改为与冻结契约一致（"所需角色即最低秩"）。`has_min_rank("operator","admin","operator")` ⇒ ValueError（`test_r11_roles.py::test_required_rank_rejects_multiple_roles`）。
- `test_r11_roles.py`：原 `test_required_rank_picks_highest_of_requested`（断言多参数 == admin）改为单参数；三态矩阵删掉两格多参数元组，原因写在用例注释里。**没有删任何单参数断言。**
- `bots.py` 8 处、`hot.py` 2 处单参数化；删除"不要抄成两个参数"那段说明注释，换成 D-V12-12 的权限边界说明。
- `test_idor_matrix.py` 基数锚：**未变**（相关用例 75 passed，未改该文件）。

## 执行中新发现 P-39（已修，同提交）
`PUT /bots/{id}` 改 `extra_config` 时**写明文**（`create_channel` 与迁移 ab1005w5b 都写密文）。读侧 `decrypt_extra_config` 对 `{` 开头的值原样返回，所以 API 看不出来，只有读库能看到。
- 先红：库里原文 `{"app_secret": "p39-marker-app-secret"}`（`p39_red_green.txt`）；修后 1 passed。
- 影响：生产库里凡是经"编辑渠道"保存过的渠道，`extra_config` 可能是明文 ⇒ 并入 STEP-07 存量审计（`SELECT count(*) FROM bot_channels WHERE extra_config LIKE '{%' AND extra_config <> '{}'`），需要时用迁移 ab1005w5b 同款逻辑重加密。

## 前端配套（`web_red.txt`）
编辑渠道表单原来总是回填并提交 `webhook_url`/`extra_config` ⇒ 运营只改名也会被凭据门整单拒绝。改为只发真正改动的凭据字段；新增 2 条 vitest，改前 2 failed，改后该文件 10 passed。按秩隐藏"新建/删除渠道"按钮仍属 STEP-15b（P-21），本卡未做。

## 改后读数
- 复跑原探针（`probe_after.txt`）：① operator GET 200 0 / POST **200 0** / PUT（只改名）**200 0**；② 两行 200 0。
- 目标集：守卫 + 矩阵 + 建任务 + P-39 + r11 = 26 passed；连同 bots 读面 / IDOR / W1 推送域 = 75 passed。
- 后端全量（`pytest_full_rs.txt`）：**1723 passed / 5 skipped / 0 failed**（410ac20 基线 1712/5/0，+11 = 本提交新增/改写的后端用例数，skip 构成不变：LangBot 2 + Redis 3）。
  - 同一工作树带覆盖率跑过一次读到 1722/6/0。独立复查已定位多出的 skip：`tests/test_env_isolation.py:77`——宿主进程没设代理变量时该用例按设计跳过（我那次后台 shell 先 `unset` 了代理变量），环境相关，非缺陷。
  - 独立复查在 434d56f 全量读数：**1728 passed / 6 skipped / 0 failed**（+5 = d1db090 新增门用例；skip 第 6 条同上）。
- ruff check 全绿；mypy app 112 文件无问题；前端 typecheck / lint / vitest 383 passed。
- ~~`git grep -nE 'require_roles\("[a-z]+", *"' apps/api/app` = 0~~ **更正（第 2 轮）**：7504ef8 上实为 **1 条**命中——`app/services/roles.py:10` 本提交自己写进 docstring 的说明文字（独立复查第 5 条 FAIL）。第 2 轮把该句改成不带引号的描述后，命令输出为空（rc=1）。

## CI-Windows skip 基线
新增连库用例 8 条（建任务 2 + 矩阵 5 + P-39 1）在 Windows 必然以「AIDEANBOT_TEST_PG_DSN 未设置」族 skip ⇒ `SKIP_BASELINE_WIN` 444 → **452**（推算值）。交付提交的 CI-Windows 读数回填本节后才算测量值。

## @ci
（交付提交推送后回填：CI / CI-Windows / Security 三条 run id、head_sha、conclusion，以及 CI-Windows 的 total_skipped。）

## 独立复查第 1 轮（2026-10-19 17:55）：总判 FAIL，2 条
- 第 5 条：上面那条 grep 不为 0（已更正，见改后读数）。
- 第 10 条：P-40 第 1 轮门修复用"值前一个字符是不是引号"判断表达式，源码里**字符串内的连接串、字符串内的环境行、注释里的赋值、反引号模板、纯数字口令**全部漏检（复查者构造 5 例，改前都报、改后 0 命中；gitleaks 对其中两类也 0 发现）。
- 第 2 轮修法：`scripts/guards.py` 新增 `_in_string_or_comment` 与 `_is_code_expression`，三条同时成立才跳过——键名不在字符串/注释里、值不带任何引号（含反引号）、值是标识符/属性/调用形。复查者 5 例 + `//` 注释 1 例写成反证用例（`test_code_mode_still_reports_shapes_inside_strings_comments_and_non_expressions`），门用例 76 passed；原表达式用例（函数调用/属性访问/设置引用）仍不报。
- 其余 11 条 PASS（含：权限矩阵 11 端点 × 3 角色逐格实测一致；夹带凭据整单拒绝且无部分生效；先授权后查库；r11 只删 2 条多参数格；Windows 基线推算 8 条正确；证据无真凭据）。
- 复查者建议请用户签字确认 D-V12-18（新建渠道仅管理员）以及"删任务、立即执行、测试推送给运营"（D-V12-12 原文未逐项写到）——已列入 V0.15.0/05 待用户确认。
