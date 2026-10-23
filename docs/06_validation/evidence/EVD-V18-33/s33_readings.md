# EVD-V18-33 · STEP-33 校验错误不回显输入值

> 基线 `main@460385c`（STEP-32 收口批之后）｜版本 V0.18.0｜队列第二项
> 归属 Agent-API｜来源 P-62｜裁决 D-V18-05

## 0. 本批改动面（对照卡面 §7/§12）

| 文件 | 改动 | 授权 |
|---|---|---|
| `apps/api/app/main.py` | 只改 `_handle_validation_error` 一个函数体 + 一行 import | §7「只改校验处理器」 |
| `apps/api/app/core/validation_message.py` | **新增**（卡面 §7 的"可选新增"那一项） | §7 |
| `apps/api/tests/test_validation_no_echo.py` | 新增 13 用例 | §7 |
| `docs/06_validation/evidence/EVD-V18-33/` | 本目录 | §7（D-V18-13） |

未动：错误码表、信封结构、`packages/contracts/**`（§13 禁止面）；
`app/api/v1/admin.py:461` 的注释里引用了旧文案「请求参数校验失败: [...]」，
该文件不在允许面 ⇒ **不改，登记在这里**（见 §6 与 P-111 附属说明）。

## 1. 开工读数（现读锚 = `460385c`）

| 锚 | 读数 |
|---|---|
| `app/main.py:127`（改前） | `body = failure(10005, f"请求参数校验失败: {exc.errors()[:1]}")`——整份错误字典进 message |
| `app/services/system_settings.py:147-158` `_readable()` | 已是正确形状（`配置形状不合法：{loc}（{type}）`），但它只覆盖**服务层** `validate()`；FastAPI 的**请求体**校验走 `main.py`，两者不同路径 |
| 卡面 §6 输入锚 `main.py:124-128` | 与现读一致（改前行号 124-128 就是这个处理器） |
| 旧文案的全仓引用 | `grep -rn '请求参数校验失败'` 在 `apps/api/tests/**`、`apps/web/**`、`packages/contracts/**` 里 **0 命中**；只有 `app/main.py`（实现）与 `app/api/v1/admin.py:461`（注释） |
| pydantic 的真实形状 | 自定义校验器 `raise ValueError(f"坏值 {v}")` ⇒ `msg='Value error, 坏值 <值>'`、`ctx={'error': ValueError('坏值 <值>')}`、`input='<值>'` ⇒ msg、ctx、input **三处都带原值** |
| 认证与校验的先后 | **先解依赖、后校体**（实测，见 §1.1）⇒ 卡面 S33.1 的泄漏面只在"已认证"路径上可达 |

### 1.1 「未认证打不到 422」的实测（这条决定用例怎么写）
五个端点各提交一次带随机凭据形值的非法体，**不带会话**：

| 端点 | 结果 | 值进响应体 | 值进日志 |
|---|---|---|---|
| `PUT /api/v1/admin/discovery/config` | 401 / 10001「缺少会话凭据」 | 否 | 否 |
| `PUT /api/v1/admin/categories` | 401 / 10001 | 否 | 否 |
| `POST /api/v1/extract` | 401 / 10001 | 否 | 否 |
| `POST /api/v1/bots` | 401 / 10001 | 否 | 否 |
| `POST /api/v1/spaces/{id}/links` | 401 / 10001 | 否 | 否 |

⇒ 「未认证时不泄漏」不是本门的功劳，是 auth 挡住了；判据必须打在**已认证**的那条路上。
这就是台账 P-111 登记的内容。

### 1.2 不连库也能打到三条真端点（本卡用例的关键可行性）
`require_roles(...)` 内部只走 `require_role(session, user_id, *roles)` →
`SqlAlchemyUserStore(session).get_by_id(user_id)` → `session.scalar(select(User).where(...))`
（`app/repositories/user.py:106-107`）。所以覆盖 `get_db` 只要给一个带 `async def scalar()` 的桩，
覆盖 `get_current_user_id` 给一个 id 即可，**不需要 PG、不需要真用户行**：

- 三条真端点在改前全部返回 **422 + code=10005**，且实测 `值进响应体=是`（三个都是），
  `值进日志=否`；
- 桩**故意不实现** `execute`/`add`/`flush`：如果哪天处理器改到"先跑端点本体再校验"，
  用例会 AttributeError 而红，不会静默地把桩扩成一个库。

## 2. S33.1 先红读数（改前实跑）

`pytest tests/test_validation_no_echo.py -q` ⇒ **8 failed / 5 passed**（56.3s）

| 失败用例 | 失败原因（=泄漏面） |
|---|---|
| `test_real_endpoints_never_echo_the_submitted_value[PUT discovery/config]` | `resp.text` 含随机值（`'input': '<值>'`） |
| `…[PUT categories]` | 同上 |
| `…[POST extract]` | 同上，且超长值被整段抄进 message |
| `test_field_name_chosen_by_the_caller_is_not_a_leak_channel` | `extra="forbid"` 的 `loc` 带着**调用方起的键名**，朴素实现照样回显 |
| `test_message_still_names_the_field_and_the_type` | 旧文案是字典 repr，`body.enabled` 这个点号路径并不存在 |
| `test_multiple_errors_report_first_path_plus_a_count` | 旧文案没有「另有 N 处」计数形状 |
| `test_probe_route_with_a_custom_validator_does_not_leak_the_interpolated_msg` | pydantic 的 `msg` 与 `ctx` 内插原值 |
| `test_no_error_dict_is_stringified_into_the_handler_source` | 源码级判据：处理器仍把 `exc.errors()` 格式化进文案 |

通过的 5 条是构造器的单元极性（不依赖 HTTP）与"检测手段自身有效"的反证，改前改后都应绿。

### 2.1 两条**假绿**被当场揪出来（这是本卡最值得留档的一段）
第一版用例跑出来是 8 failed / 5 passed，但其中两条其实是绿的，原因是我的写法而不是实现：
1. 探针模型定义在**测试函数内**，而本文件带 `from __future__ import annotations`
   ⇒ FastAPI 拿不到那个局部类的注解，请求以**另一种** 422 失败，`marker` 自然不在文本里 ⇒ 假绿。
   改法：模型提到模块级（`_InterpolatingProbe`），并在用例里先把前提钉住
   ——`assert marker in str(errors)` 与 `assert marker in str(errors[0]["ctx"])`，
   前提一旦不成立用例立刻红，而不是静默失去判定力。
2. 用 `app.routes` 爬路由表断言三条路径存在：现读 FastAPI 把 include 的路由包成
   `_IncludedRouter`（属性是 `original_router`，**没有** `.routes`）⇒ 我的推导式得到空字典，
   `path in {}` 恒假 ⇒ 这条用例是**假红**（而另一种写法会把它写成"空集=全过"=假绿）。
   改法：改走公开面 `create_app().openapi()["paths"]`，并在断言消息里写明"前提已过期"。

## 3. S33.2 实现与三条设计决定

新文案形状（示例用合成值）：`请求参数校验失败：body.enabled（list_type）：应为列表`
多条时追加 `；另有 N 处不合法`，只展开第一条（与旧实现的 `[:1]` 同口径，不铺开）。

1. **不用 pydantic 的 `msg` 原文**：原因文案由 `REASONS` 按 `type` 给固定句。
   除了防内插，还防"上游改一句措辞 ⇒ 对外文案跟着变而没人红"。
2. **未知 `type` ⇒ 泛化原因，绝不退回 msg**：判据不能建立在"上游不会新增会内插的类型"上。
   带后缀的类型（`value_error.*`）按前缀认。
3. **路径段做形状约束**：只放行标识符形状的段名与整数下标，其余换成「字段」——
   因为 `extra_forbidden` 一类错误的 `loc` 里是**调用方自己起的键名**。
   （实测：把随机值当键名提交，改前会原样回显 ⇒ §2 表第 4 行。）

`input` 与 `ctx` 在本模块**一次都不读**（源码里没有这两个键的取值点，只有 `loc`/`type`）。

## 4. S33.3 全量回归与"改期望的用例清单"

- **清单 = 空集**。依据是 §1 的全仓引用读数：旧文案「请求参数校验失败」在测试、前端、契约里
  都没有被断言过（0 命中）；断言过 `resp.json()["message"]` 的 9 个位置逐条查过，
  它们的 needle 全部来自**服务层** `RequestInvalidError` 的自有文案（渠道未注册、关键词、引用数、
  双主密钥未配置等），不走本次改动的处理器。
- 前端 `apps/web/tests/**` 里出现的 10005 都是**自造 mock 文案**（如「请求参数不合法」），
  与后端文本无耦合 ⇒ 不破。
- 全量读数：本地 1631/666/0 failed、@ci 2291/6/4、@win 1631/666 —— 全部记在 §5 与 §6。

## 5. 门禁读数

| 门 | 读数 |
|---|---|
| `ruff check app tests` | All checks passed（第一版报 UP038 一处，已把 isinstance 的第二参数改成联合写法） |
| `mypy app` | Success: no issues found in **120** source files（新模块进了口径；第一版因形参写窄了报一处 arg-type，已把入参放宽成序列） |
| `pytest tests/test_validation_no_echo.py -q` | 改前 **8 failed / 5 passed** ⇒ 改后 **13 passed**（56.2s / 56.1s） |
| 本地全量 `pytest tests/ -q -x --timeout=600` | **1631 passed / 666 skipped / 4 deselected / 0 failed**，1140.23s（19:00），rc=0 |
| 三绿（同一 head `c9287a6`、attempt 1） | CI 39923572062 success（backend 20/20、frontend、workflow-lint、compose、compose-smoke 全成）；CI-Windows 39923572072 success；Security 39923572102 success |

### 5.1 本地全量这一发为什么重要（它顺手验了 CI-Windows 的零余量门）
本机是 Windows、无 PG 监听（`AIDEANBOT_TEST_PG_DSN` 未设置）⇒ 与 `@win` job 同一形状。
这个推断后来被 `@win` 自己证了（run 39923572072，同一 head）：

```
本地全量           1631 passed / 666 skipped / 4 deselected        （1140.23s）
@win @c9287a6      1631 passed / 666 skipped / 4 deselected        （win:650，1117.63s）
@win 门禁           failed=0 total_skipped=666 baseline=666        （win:720）
@win @da09dd1      1618 passed / 666 skipped                        → +13 正好是本卡用例
```

⇒ 三处读数两两相等，本卡**没有新增任何 skip**，`SKIP_BASELINE_WIN` 不必抬（那道门零余量，
多一条连库 skip 就会红）。这正是 §1.2 选择"桩会话而不是连库夹具"的直接后果，写在这里是为了让后来人知道
这个选择不是风格问题，是判据面问题（D-V10-11）。

### 5.2 一条本机全量的读法提醒
`--timeout=600` 那一发跑到 19 分钟，中途 stdout 是空的（管道里的 `tail` 会把整段缓冲到最后）⇒
"没有输出"不等于"卡住"，也不等于"通过"；判据取的是最后一行的计数与 rc=0，两者都记在上面。

## 6. @ci 内的两条直接证据

- **计数**（run 39923572062，`0_backend.txt`）：`ci:918` =
  `2291 passed, 6 skipped, 4 deselected, 2 warnings in 220.90s`，`ci:910` = `Total coverage: 88.05%`，
  `ci:919-920` = `skip 门禁：total_skipped=6 baseline=6 pg_unreachable=0` ⇒ 通过。
  2291 = 上一 head 的 2278 + 本卡 13 条，**逐条对得上**；覆盖率仍是 P-104 那条抖动带里的数
  （88.01/87.95/88.00/87.96/88.02/88.05 六个点），只用来过 79 线，不当精确判据。
- **上一卡那道门仍在 CI 里跑**（与本卡无关但同一屏可读）：`ci:1145-1148`
  `guard-ci-secret-mask rc=0`。
- 静态门：`ci:510` ruff `All checks passed!`、`ci:511-512` `mypy app`（无 error 行 ⇒ 通过，
  job 结论 success 是终判）。

## 7. 收口判定（D-V18-15 的覆盖面）

| 判据 | 读数 | 结论 |
|---|---|---|
| S33.1 先红（三条真端点 + caplog） | 8 failed / 5 passed ⇒ 13 passed | ✅ |
| S33.2 处理器只拼 loc + type + 原因，不读 input/ctx | `validation_message.py` 全文没有 `input`/`ctx` 的取值点；未知类型走泛化句 | ✅ |
| S33.3 全量回归 + 改期望用例清单 | 本地 1631/666/0 failed；@ci 2291/6/4；@win 1631/666；清单=**空集**（§4 的 0 引用依据 + 9 处 message 断言逐条查） | ✅ |
| `grep -n "exc.errors()" main.py` 不再把整份字典格式化进 message | 常驻用例 `test_no_error_dict_is_stringified_into_the_handler_source` 做源码级判 | ✅ |
| 全量 0 failed + 三绿 | §5 表 | ✅ |
| 卡面 §12「现有断言 10005 文案的用例只许改期望、不许删」 | 本批**未删也未改任何既有用例**（因为 0 条断言这段文案） | ✅（空面，如实记） |
| 继承增量表 | `STEP-继承卡增量-V0.18.md` 无 STEP-33 行 ⇒ 零项 | ✅（空面） |
| 卡面自身增量 | STEP-33 无卡面增量节 ⇒ 零项 | ✅（空面） |

## 8. 登记

- **P-111**（本批已进台账）：卡面 S33.1 要求"对三个真实端点提交非法请求"，现读证明**未认证时该面不可达**
  （认证依赖先于请求体校验，5 个端点实测全部 401/10001）⇒ 判据只在已认证路径上有意义。
  本卡用桩会话（覆盖 `get_db` 的 `scalar` + `get_current_user_id`）在不连库的前提下打到真端点，
  这样既不抬 CI-Windows 的零余量 skip 基线，也能在本机复现先红。
  要不要把"未认证也不得泄漏"单独做成一条判据（例如给 10001 的文案也加同形约束），交规划方裁定。
- **P-112**（收口批新登记）：**调用方可控文本进日志还有两条本卡没管的路**——
  ① `app/core/audit.py:83` 把 `path_params=dict(scope["path_params"])` **原样**写进审计日志，
  路径段是调用方控制的（`/spaces/{space_id}/links` 里塞什么就记什么）；
  ② structlog/httpx 的访问行记完整 URL，query string 也在其中（本卡探针里就能看到整行 URL）。
  两者都不在"422 不回显"这一条判据的面上，但它们是 P-62 的同一族：**调用方的值进日志**。
- 附属一条（不另开 P 号）：`app/api/v1/admin.py:461` 的注释仍在引用旧文案，
  该文件不在 STEP-33 允许面 ⇒ 未改。

## 9. 原始件 `s33_message_contrast.txt` 的读法（3.0 KB）
同一条 payload 的两行对照：**改后文案**取真实 HTTP 响应，**旧写法**由探针把该端点请求模型
直接 `model_validate` 得到 errors 再按旧写法格式化——两行的 `loc` 差一层 `body` 前缀（那是
FastAPI 加的），泄漏与否看的是 `input`，与层数无关。四行结果：

| 输入形状 | 改后文案 | 标记出现在改后 / 旧写法 |
|---|---|---|
| `enabled` 给成字符串 | 请求参数校验失败：body.enabled（list_type）：应为列表 | False / True |
| `categories` 给成字符串 | …：body.categories（list_type）：应为列表 | False / True |
| `url` 超长（600+ 字符） | …：body.url（string_too_long）：长度超过上限 | False / True |
| 键名就是那个随机值 | …：body.enabled（missing）：缺少必填字段；另有 2 处不合法 | False / True |

顺带三条现读事实（本卡不管，写给 STEP-34/37 的读者）：
- pydantic 2.14 的 errors 字典里还多一个 `url` 键（值形如 `errors.pydantic.dev/2.14/v/list_type`），
  旧写法把它也一并端进响应 ⇒ 旧文案动辄 200-300 字符；新文案与 pydantic 版本无关。
- 最后那行的旧写法里 `input` 是**整个 body 字典**（形如 `{'<随机值>': 1}`），
  所以"把凭据串当键名"这种绕过方式也一样被抄出去——这正是 §3 第 3 条要给路径段加形状约束的原因。
- **本节第一版是被 shell 引号吃掉后写进文件的**：反引号里的术语全变成空白，句子却照样通、
  表格照样齐。记在这里是因为这类失真不报错——凡带反引号或 CJK 的文档写入一律用编辑工具，
  不用 `python -c "…"` 拼字符串。
