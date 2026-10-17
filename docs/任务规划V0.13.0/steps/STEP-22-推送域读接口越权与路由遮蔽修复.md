# STEP-22 推送域读接口越权与路由遮蔽修复（V0.13.0 新增 · P0 安全）

> 状态：**🟡 6 个三级任务已交付，第一轮独立验证判 FAIL 后已返工**（2026-10-17）。四支读接口已加
> `require_roles("admin","operator")`、`/tasks*` 已前置、两道防复发守卫在位（遮蔽守卫已从硬编码
> 改成**枚举路由表**，并用一发"在 `/{channel_id}` 之后新增静态段"的注入证明它会红）。
> 读数、前端调用点分析与返工全过程在 `docs/06_validation/evidence/EVD-V13-22/s22_readings.md`（§1–§9）。
> **仍未 Done**：验收里「探针不再是 200」与「真库全量 `failed = 0`」两条只能由 `@ci` ubuntu 判
> （本机无 PG，5 条连库用例 skip；skip ≠ 通过）。
> 残余 UX 缺陷（`/bots` 入口只按登录门禁）已发布为 **P-21**，归 STEP-15b/14b；本卡禁止改 `apps/web/**`。

| 字段 | 值 |
|---|---|
| 归属-切片 | S-M0 前提固定（安全缺陷，阻塞任何对外部署） |
| 归属-需求 | 冻结契约 `docs/任务规划V0.12.0/contracts/identity.schema.json`：角色 `user/operator/admin`，`x-default: user`，授权走 rank 比较；`bothot_entities.py:22-23` 注释"webhook_url 和 secret 由管理员在后台填写，AES-256-GCM 加密落库"；`bots.py:47-49` 注释"渠道 CRUD / 测试推送 / 日志含 webhook 与密钥" |
| 归属-方案 | D-V10-07（本版代选：推送域全部读接口与写接口同级，rank ≥ operator）；D-V10-08（`GET /bots/tasks` 路由前置） |
| 里程碑 | M0（与 00H 并列 P0） |
| 执行者 | **规划方**（安全审查属高难度核心；判"谁该看得见密钥"不能交给中等档） |
| 档位 | opus　理由：授权边界决策 + 前端读路径影响评估；改错一侧要么继续泄密、要么把运营挡在门外 |
| 规模 | 中（≈1.0 人日；6 个三级任务） |
| 依赖 | Depends on：无　Blocks：21（IDOR 矩阵把本卡的规则当基线）、14b（管理端推送屏要能读到任务列表） |
| 基线 | main@314d7f2 |

## 证据链
1. **越权读出明文密钥（已在真库复现）。** 用 `dependency_overrides` 注入一个**无角色的普通登录用户**，向测试库播种一条飞书渠道（`webhook_url` 含令牌、`extra_config` 含 `app_secret` 并按生产路径 AES 加密）：
   `GET /api/v1/bots/{id}` → 200，响应含 webhook 令牌 **且含解密后的 `app_secret`**；`GET /api/v1/bots?page_size=100` → 同样两者皆漏；对照组 `PUT /api/v1/bots/{id}` → 401/10001（有 `require_roles`）。
   （证据 `evidence/314d7f2/probe_bots_read_by_plain_user.{py,txt}`；探针只读，结束时删除播种行）
2. **原因在代码里一眼可见。** `bots.py:44-52` 的 router 只挂了 `Depends(get_current_sub)`（登录门）；`list_channels`(:216)、`get_channel`(:250)、`list_push_logs`(:372)、`list_push_tasks`(:479) **四个读接口都没有 `require_roles`**，写接口（:259 PUT 等）都有。`_serialize_channel`(:113-129) 回显 `webhook_url` 原文与 `decrypt_extra_config(...)` 明文；`bothot_entities.py` 注释写明 `extra_config` 存"飞书 app_id/app_secret、钉钉 access_token 等"。而新用户默认角色就是 `user`（identity 契约 `x-default: user`）⇒ **任何能完成 SSO 的人都能拿到所有推送渠道的凭据**。
3. **`GET /api/v1/bots/tasks` 永远 404。** `/{channel_id}`(:250) 声明在 `/tasks`(:479) 之前，FastAPI 按声明序匹配 ⇒ 请求被 `get_channel` 吃掉，返回 `30004 渠道不存在: tasks`（证据 `evidence/314d7f2/route_shadow_bots_tasks.txt`：首个 FULL 匹配 = `get_channel`；探针同样读到 404/30004）。前端 `apps/web/lib/api/bots.ts:182` 正在调它 ⇒ 推送任务列表页**在真实后端下必然是错误态**；`tests/` 中没有任何用例 `GET /bots/tasks`（`grep -rn "bots/tasks" apps/api/tests` 只有 `test_security_middleware.py:245` 的 `/run` 限流键），所以 1478 条全绿也没抓到。

## 反证（钢人）
- **反 1："这是单租户内部工具，登录的都是运营。"** 契约明写默认角色 `user`、rank 0，写接口也按 operator 设了门；如果"登录即运营"成立，写接口的 `require_roles` 就是多余的。代码自身的设计意图是分级的 ⇒ 读接口漏门是缺陷而不是设计。**残余不确定**：生产上普通用户是否真的能登录（取决于 SSO 白名单）`证据不足`，但不影响修复方向。
- **反 2："webhook_url 相当于门牌号，可以明文"**（`bothot_entities.py` 注释原话）。飞书/钉钉/企业微信的 webhook URL 本身就是投递凭据（持有即可向群里发消息）；且 `extra_config` 的 `app_secret` 被同一响应**解密**回显，这一条无论怎么解释 webhook 都成立。
- **反 3：加门会不会挡掉前端现有页面？** 前端 `/bots` 页本就是管理功能；本卡 S22.2.2 先列出前端所有 `/api/v1/bots*` 调用点并确认其使用者角色，再落门。

## 目标（可验证的一句话）
rank < operator 的登录用户访问推送域任一读接口得 `403/10004` 且响应体不含任何渠道字段；`GET /api/v1/bots/tasks` 对 operator 返回 200 与分页任务列表。

## 输入
- 证据：`evidence/314d7f2/probe_bots_read_by_plain_user.{py,txt}`、`route_shadow_bots_tasks.txt`
- 契约：`docs/任务规划V0.12.0/contracts/identity.schema.json`（角色与 rank、`x-idor-checklist`）、`docs/任务规划V0.12.0/contracts/errors.global.schema.json`（10004）
- 前置状态：无

## 输出（文件）
- 改：`apps/api/app/api/v1/bots.py`（四个读接口加 `require_roles("admin","operator")`；`/tasks` 系列路由整体移到 `/{channel_id}` 之前）
- 新：`apps/api/tests/test_bots_read_authz.py`
- 证据：`docs/06_validation/evidence/EVD-V13-22/`

## Execution Steps
### S22.1 先红
1. [x] **S22.1.1** 把探针改写成 pytest（`db_session` 夹具 + `dependency_overrides`）：①无角色用户读四个接口 → 期望 403/10004 且响应文本不含播种令牌；②operator 读 `GET /bots/tasks` → 期望 200 且 `data.items` 是列表。在 314d7f2 上跑出**红**（①得 200、②得 404）
   - ✅ 本机读数（`ef63bf9` 上跑改前代码）：`2 failed, 3 passed, 5 skipped`——红落在两道**结构性**守卫上（四支漏门读接口被逐个点名；`GET /bots/tasks` 首个 FULL 匹配 = `get_channel`）。连库那 5 条本机 skip，卡面原设计的"①得 200"由 `@ci` 复现。EVD §1
### S22.2 修
2. [x] **S22.2.1** `bots.py`：把 `@router.post("/tasks")`、`@router.get("/tasks")`、`/tasks/{task_id}` 三个及 `/run` 的定义块整体上移到 `@router.get("/{channel_id}")` 之前（只移动，不改函数体）；在 `/{channel_id}` 上方留一行注释说明顺序约束
   - ✅ 用带防呆的脚本移动（锚点整行唯一 + 移动前后代码行**多重集**相等 + 装饰器集合相等 + `ast.parse`）：`549 → 552` 代码行，丢失 0，新增只有那 3 行顺序注释。`test_idor_matrix.py` 的 93/47/31 基数锚不变
3. [x] **S22.2.2** 列出前端全部 `/api/v1/bots*` 调用点（`grep -rn "/api/v1/bots" apps/web/lib apps/web/app`）及其页面，写进 EVD；确认均位于需 operator 的管理页
   - ✅ 14 个调用点 + `apps/web/app/bots/page.tsx` / `PushTasksTab.tsx` / `TopBar.tsx:120` 已入 EVD §4。**卡面那句"确认均位于需 operator 的管理页"只成立一半**：`/bots` 是管理页，但导航项 `PrivateNavItem` 只按**登录**门禁 ⇒ 残余 UX 登记为 **P-21**（本卡禁止改 `apps/web/**`）。阻塞条件（普通用户功能依赖这些读接口）**未触发**，不走 fable 升级
4. [x] **S22.2.3** 四个读接口加 `_: str = Depends(require_roles("admin", "operator"))`（与同文件写接口同形）；`list_channel_types`(:166，只回类型枚举、不含实例数据) **不加**，在 EVD 写明理由
   - ✅ 四支齐；**但门写成 `require_roles("operator")` 而不是卡面说的"与同文件写接口同形"**——`_required_rank` 取的是请求角色里的最高秩（`roles.py:44` `max(...)`），所以照抄`require_roles("admin","operator")` 会要求 admin，卡面目标句「operator 得 200」永不成立（`@ci` run 39016275296 实测 operator 拿 403/10004）。写接口那 8 处的 admin-only 现状连同待裁决点登记为 **P-23 / D-V10-09**，`roles.py` 与 `deps.py` 是本卡禁止修改面。白名单理由 + "类型枚举里没有任何实例数据"的断言入 EVD §5 与 `test_channel_types_stays_readable_for_a_plain_user`。另更正 `_serialize_channel` 的假文案（原写"不暴露 secret"，实际回显 webhook 与解密后的 `extra_config`），见 EVD §6
### S22.3 防复发
5. [x] **S22.3.1** 在新测试文件加"路由面守卫"：枚举 `app.routes` 中前缀 `/api/v1/bots` 的所有 GET/PUT/POST/DELETE（复用 `tests/test_idor_matrix.py` 的递归摊平写法），除白名单 `list_channel_types` 外每个端点的依赖树必须含 `require_roles` ⇒ 将来新增读接口忘加门会红
   - ✅ `_ordered_bots_routes()` 走 `.original_router.routes` 摊平（照 `test_idor_matrix.py` 那条已踩过的坑）；反证已做：临时删掉 `list_channels` 那道门 ⇒ 守卫红、判据自检仍绿，还原后 sha 一致（EVD §3）
6. [x] **S22.3.2** 新测试文件再加"路由遮蔽守卫"：对 `/api/v1/bots` 下每个静态段路径（如 `/tasks`、`/channels`），断言首个 FULL 匹配的 endpoint 就是它自己
   - ✅ 三条参数化（`/bots`、`/bots/channels`、`/bots/tasks`）全绿；改前只有 `/bots/tasks` 红，说明判据有区分度而不是一刀切

## 验收标准（2026-10-17 执行后逐项状态）
- [~] 新测试在 314d7f2 红、本卡提交绿（两份原始输出入 EVD）—— **部分确认**：两道结构守卫的红/绿两份本机读数已入 EVD §1/§2；但连库那一半**从未绿过**，且第一轮独立验证查出我的测试假面接错了授权入口（`get_current_sub` 未覆写 ⇒ 到不了角色门），已返工重写（EVD §9），待 `@ci` 复跑
- [ ] `python evidence/314d7f2/probe_bots_read_by_plain_user.py` 前两行不再是 200，且两列 `leaks` 均为 `False`（探针注入的身份不在 `users` 表，`require_roles` 经 `get_current_user_id` 会先给 `401/10001`——与对照组 PUT 同形；带真实 `users` 行、role=user 的 403/10004 判据由 S22.1.1 的 pytest 负责）—— `待 @ci`（本机无 PG）
- [x] 路由面守卫的反证：临时删掉任一读接口的 `require_roles` ⇒ 守卫红（输出入 EVD，然后还原）—— 已做，还原经 sha256 校验
- [ ] 真库全量 `failed = 0`；`@ci` `CI` success —— `待 @ci`
- [x] `git diff --name-only` ⊆ "输出"清单 —— 改动落在 `apps/api/app/api/v1/bots.py`、`apps/api/tests/test_bots_read_authz.py`（新）、`docs/06_validation/evidence/EVD-V13-22/**`；文档面（卡、04 表、README P-21、08 执行记录）按"代码改动必须同步到文档"的总纪律同更，未越界改 `apps/web/**`、`deps.py`、`roles.py`、`secret_crypto.py`、契约与冻结稿

## 验证命令
```bash
cd apps/api && . .venv/bin/activate
export AIDEANBOT_TEST_PG_DSN=postgresql+psycopg://postgres@127.0.0.1:5547/bothot_test
export PUSH_SECRET_MASTER_KEY=$(python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())")
python -m pytest tests/test_bots_read_authz.py tests/test_bots_logs_filter.py tests/test_w1_push_domain.py -q
python ../../docs/任务规划V0.13.0/evidence/314d7f2/probe_bots_read_by_plain_user.py 2>&1 | grep -E "^/api|^PUT"
```

## 证据路径
`docs/06_validation/evidence/EVD-V13-22/`

## 允许修改
- `apps/api/app/api/v1/bots.py`
- `apps/api/tests/test_bots_read_authz.py`（新）
- `docs/06_validation/evidence/EVD-V13-22/**`

## 禁止修改
- `apps/api/app/api/deps.py`、`apps/api/app/services/roles.py`（授权机制本身不动，只是补用）
- `apps/api/app/core/secret_crypto.py`（加密面不动）
- `packages/contracts/**`、`docs/任务规划V0.12.0/contracts/**（冻结稿，被测试硬绑定，见 03 D-V10-06）`
- `apps/web/**`（前端不需要改；若 S22.2.2 发现普通用户页面在调这些接口，**停下**走升级条件）

## 依赖与阻塞
- Depends on：无
- Blocks：21、14b
- 阻塞条件：S22.2.2 发现面向 `user` 角色的页面依赖这些读接口 ⇒ 不能简单加门，需要裁决"给普通用户的脱敏视图"

## 建议执行档位
opus　理由：安全边界

## 升级条件
上述阻塞条件触发 ⇒ fable 一次，裁决是否新增 `GET /bots/{id}` 的脱敏投影（这会改契约）

## 预估规模
中　6 个三级任务，单个 < 2h；≈1.0 人日
