# EVD-V13-22 · STEP-22 推送域读接口越权与路由遮蔽（执行方读数）

基线：`main@ef63bf9`（V0.13.0 规划树，卡 = `docs/任务规划V0.13.0/steps/STEP-22-*.md`）
执行机器：`@win`（Windows 10.0.19045，无 PG / 无 Redis / 无 LangBot）
执行时间：2026-10-17 17:2x–17:5x Asia/Shanghai

## 1. 先红读数（S22.1.1，改前）

命令：
```
cd apps/api && .venv/Scripts/python.exe -X utf8 -m pytest -q -p no:cacheprovider \
  --timeout=90 tests/test_bots_read_authz.py
```

原始读数（本机可判的那两道守卫当场红，连库那 5 条 skip）：

```
FAILED tests/test_bots_read_authz.py::test_every_bots_operation_except_the_whitelist_has_a_role_gate
FAILED tests/test_bots_read_authz.py::test_static_bots_paths_are_not_shadowed_by_the_param_route[/api/v1/bots/tasks]
2 failed, 3 passed, 5 skipped
```

守卫点名的四支漏门读接口（与规划方卡面 §证据链 2 逐个对应，非我推断）：

```
['GET /api/v1/bots -> list_channels',
 'GET /api/v1/bots/{channel_id} -> get_channel',
 'GET /api/v1/bots/{channel_id}/logs -> list_push_logs',
 'GET /api/v1/bots/tasks -> list_push_tasks']
```

遮蔽守卫的红读数（首条 FULL 匹配落在通配路由，正是 314d7f2 探针的 `404/30004` 之因）：

```
AssertionError: GET /api/v1/bots/tasks 的首个 FULL 匹配落在 /api/v1/bots/{channel_id}（get_channel）⇒ 被遮蔽
```

另外两条静态路径（`/api/v1/bots`、`/api/v1/bots/channels`）当场就过——它们本就声明在
`/{channel_id}` 之前，所以这条守卫不是一刀切地把三个都判红，判据有区分度。

## 2. 改后绿读数

```
5 passed, 5 skipped in 32.13s          # tests/test_bots_read_authz.py
46 passed, 11 skipped, 0 failed        # + test_bots_logs_filter / test_w1_push_domain / test_idor_matrix
```

`test_idor_matrix.py` 的三个基数锚（93 操作 / 47 带参数 / 31 落稿面）在路由重排后**仍然成立**，
证明 S22.2.1 是纯移动、没有增删端点。

## 3. 反证（S22.3.1 的验收要求：临时删一道门 ⇒ 守卫必须红）

做法：把 `list_channels` 签名里的 `_: str = Depends(require_roles(...))` 一行删掉，跑守卫，然后还原。

```
FAILED tests/test_bots_read_authz.py::test_every_bots_operation_except_the_whitelist_has_a_role_gate
1 failed, 1 passed            # passed 的那条是 test_role_gate_predicate_itself_has_teeth
```

还原校验：`grep -c 'require_roles("admin", "operator")' app/api/v1/bots.py` = **12**
（8 支写接口 + 本卡新加的 4 支读接口），`sha256sum` 与动手前的工作副本一致。

判据本身的两个极性由 `test_role_gate_predicate_itself_has_teeth` 钉：
①已知有门的 `PUT /bots/{channel_id}`、`POST /bots/{channel_id}/test` 必须判 True（认不出＝守卫是空的）；
②给一个依赖树为空的假路由必须判 False（判据恒真＝第 1 节的绿没有含义）。

## 4. S22.2.2 前端调用点清单（落门前必须确认使用者角色）

`grep -rn "/api/v1/bots" apps/web/lib apps/web/app apps/web/components` 的**全部**命中：

| 调用点 | 端点 | 落门后的影响 |
|---|---|---|
| `apps/web/lib/api/bots.ts:74` | `GET /bots/channels` | **不加门**（只回类型枚举，前端新建渠道的下拉框要用）——白名单，见 §5 |
| `:89` | `GET /bots` | 普通用户改为 403 |
| `:93` | `GET /bots/{id}` | 普通用户改为 403 |
| `:103/:119/:126` | `POST`/`PUT`/`DELETE /bots...` | 无变化（本来就有门） |
| `:138` | `POST /bots/{id}/test` | 无变化（本来就有门） |
| `:151` | `GET /bots/{id}/logs` | 普通用户改为 403 |
| `:166/:182` | `POST`/`GET /bots/tasks` | GET 从"恒 404"变为 operator 可读 |
| `:196/:203/:207` | `PUT`/`DELETE`/`POST run /bots/tasks/{id}` | 无变化（本来就有门） |

页面侧：`apps/web/app/bots/page.tsx` + `apps/web/components/PushTasksTab.tsx`，导航项在
`apps/web/components/TopBar.tsx:120` 是 `<PrivateNavItem href="/bots" …>`——**只按登录门禁，未按角色门禁**。

结论与后果判断：

- `/bots` 是管理控制台（渠道凭据 + 推送任务），**不是**普通用户功能面；而它的**写**接口
  （建渠道、改渠道、测试推送、建/改/删/跑任务）在改前就要求 `role ≥ operator`，
  所以"能正常使用这个页面"的人群本来就等于"已被显式授予 operator"的人群——落读门
  不会把任何原本能干活的运营挡在门外。本地角色默认 `user`（`app/models/entities.py:28`），
  `has_min_rank` 对脏值/缺角色 fail closed（`app/services/roles.py:46-54`）。
- **残余 UX 缺陷**：`role=user` 的登录用户点"机器人"导航仍进得去页面，进去之后从
  "看见本该看不见的凭据"变成"看到 403 错误态"。这是正确方向，但入口不该暴露 ⇒
  登记为 **P-21**（前端按秩隐藏入口 + 无权页），归 STEP-15b/14b 的前端面；
  本卡的"禁止修改 `apps/web/**`"是硬约束，故不动前端。
- 卡面的阻塞条件（"发现面向 `user` 角色的页面**依赖**这些读接口"）**未触发**：
  没有任何普通用户的正当功能依赖这些读接口。故不需要走 fable 升级裁决"脱敏投影"。

## 5. 白名单为什么只有 `list_channel_types`

`GET /bots/channels` 返回 `registered_channels()`（渠道**类型**枚举 + 展示字段），
不含任何 `BotChannel` 行、不含 webhook/secret/extra_config（用例
`test_channel_types_stays_readable_for_a_plain_user` 同时断言响应文本里
没有播种的两支凭据标记）。给类型枚举加角色门会把普通用户的"新建渠道"表单打死，
而类型清单不是凭据面。

## 6. `_serialize_channel` 的文案更正（不是顺手清理，是判据前提）

函数原 docstring 写「序列化渠道（不暴露 secret）」，而 :119 回显 `webhook_url` 原文、
:122 回显 `decrypt_extra_config(...)` 的明文。飞书/钉钉/企业微信的 webhook URL **本身就是投递凭据**。
文档与代码相反会让人以为"读接口不需要角色门"——那正是本卡缺陷的认知根源，故改为如实描述，
并在其中写明：**这两个字段只暴露给 operator 及以上，角色门是这份回显成立的前提**（D-V10-07）。

## 7. 本机判不了 / 需要 @ci 的判据

- 5 条连库用例（403/10004 全套、operator 读详情与任务列表、未登录 401、白名单仍可读、播种行夹具隔离）
  在无 PG 的机器上 skip：`skip ≠ 通过`，Done 面是 `@ci` ubuntu。
- 卡面验收的「`probe_bots_read_by_plain_user.py` 前两行不再是 200、两列 leaks 均 False」需要真库，交 `@ci`。
- 卡面验收的「真库全量 `failed = 0`」同上。

## 8. 顺带取得的一条 STEP-00H 读数（不属于本卡，记在此处以免丢）

本机 `tests/test_security_middleware.py` **整文件跑不完**：47 条里有 5 条
`_client().get(HEALTH_PATH)`（`:335`、`:345` 等），在无 PG 的 Windows 上**无限挂起**
（`timeout 70` 直接被杀，连 pytest 汇总行都没有）。已证明与本卡改动无关：
把 `apps/api/v1/bots.py` 临时换回 `HEAD` 版本后，同一条用例同样挂死（还原后 sha 一致）。

这给 STEP-00H 的 **H2** 增加两条独立事实：
①受害者不止 `test_envelope.py` 的 3 条，`test_security_middleware.py` 另有 5 条打 `/health`；
②在 `@win` 本机（不是 CI-Windows）也复现了"`/health` 不返回"，与"PG 探针无
`connect_timeout` + Windows 回环不回 RST"的机制预测一致。`部分确认` 的那半截
（"CI-Windows 上就是它"）仍只能由 `@ci` 判。

## 9. 第一轮独立验证判 FAIL，与本轮返工（2026-10-17 18:0x）

验证者（30 次调用预算内，用了 34 次）总体判定 **FAIL**：本卡的**代码改动本体**经它独立复核
"正确，无需返工"，红在**我的判据面**。四条逐条处置：

| # | 验证者的发现 | 我的复核 | 处置 |
|---|---|---|---|
| D-1 (P1) | `_client()` 只覆写 `get_current_user_id`，而 `bots.py:51` 在 **router 层**挂了 `dependencies=[Depends(get_current_sub)]`；它本机实测三条路径全回 `401/10001`（会话校验早于任何 DB 访问）⇒ 403/200 断言**到不了角色门**，CI 上必红 | 成立。我自己读了 `bots.py:46-51` 与 `deps.py:61-69`（`get_current_user_id` 本身依赖 `get_current_sub`），结构上不可能被单覆写绕过。`test_discovery.py:227` 那个"只覆写 user_id"的先例属于**没有 router 级依赖**的 admin 面，不能照抄 | `_client()` 改为覆写 `get_current_sub = lambda: user.sub`，让 `sub → users 行 → has_min_rank` 这条**真实授权链**跑完（顺带证明 P-21 担心的口径不同源没发生在后端） |
| D-2 (P2) | 无正控 ⇒ 普通用户那条"响应体不含凭据"是**恒真断言**——403 的响应体本来就没有渠道字段 | 成立，且这正是本仓库反复登记的那族错（判据只会陪绿） | 在 operator 那条用例里加两行正控：`_MARKER_WEBHOOK in detail_text` 与 `_MARKER_SECRET in detail_text`。没有正控，"泄露已封堵"和"接口压根没返回数据"读成同一个绿 |
| D-3 (P3) | 遮蔽守卫是 `@pytest.mark.parametrize` **硬编码三条** ⇒ 将来新增静态段却声明在 `/{channel_id}` 之后时不会红，是装饰 | 成立。一条防"复发型态"的守卫如果判据面不随路由表增长，它就只防住了历史 | 改为 `_static_bots_get_paths()` 从路由表**枚举**静态段 GET；另加两条自锁：枚举为空即红、`/bots/tasks` 必须在枚举面内。**极性已证**：在 `/{channel_id}` 之后注入一条 `@router.get("/newadmin-only-path")` ⇒ 守卫当场 `1 failed`，随后逐字删除并 `grep` 证明无残留 |
| D-4 (P3) | 角色守卫放过 HEAD/OPTIONS；`bots.py` 尾部多 3 个空行 | 放过 HEAD/OPTIONS 是对的（Starlette 为 GET 自动加 HEAD，router 层登录门对所有方法生效），不改；尾部空行是我的移动脚本多写的 | 尾部收敛为单个换行（`bytes 22712 → 22706`），ruff 全绿 |

另两条验证者给的"文档偏乐观"提醒也照改：卡面第 1 条验收从 `[x]` 降为 `[~] 部分确认`
（连库那半从未绿过），卡头状态从"🟢 全部交付"降为"🟡 已交付 + 已返工，Done 仍待 `@ci`"。

返工后本机读数：`tests/test_bots_read_authz.py` = `3 passed / 5 skipped`（5 条连库仍只能由
`@ci` 判），ruff 全绿。**D-1 是这条判据链上唯一的阻断项**，它修好之前，"P0 已封堵"这句话
在本卡上只有结构守卫作保、没有端到端作保——所以状态仍是 `部分确认` 而不是"已确认"。
