# STEP-25 角色门单参数化：运营写权按调用意图恢复（P0 授权语义）

| 字段 | 值 |
|---|---|
| 1 执行者 | **规划方(Hark) 自做**（安全语义、跨 3 个路由文件、改 roles.py） |
| 2 验收者 | 独立验证 Agent（PASS / FAIL / UNKNOWN）+ 安全复核一轮（opus 券 1） |
| 3 难度 / 里程碑 | 高 / M0-P0 |
| 4 所属切片 | SL-PUSH-1 / SL-OPS-1「运营执行热点聚簇与日报生成」 |
| 5 来源 | D-V10-04（B 类 rank≥operator）、D-V10-09、P-23、**D-V11-01** |
| 6 证据 | `evidence/fdad6dd/probe_push_write_roles_and_created_by.txt` ①：operator `GET /bots/tasks` 200，`POST /bots/tasks` 与 `PUT /bots/{id}` **403/10004**；`has_min_rank("operator","admin","operator") = False` |
| 7 档位 | opus；升级条件：任何调用点的意图无法从代码/需求读出 ⇒ 停并登记，不得猜 |
| 8 规模 | 中，6 项，约 1.2 人日 |

## 0. 目标
仓内不再存在多参数 `require_roles(...)`；原写作 `("admin","operator")` 的 10 个端点（`bots.py` 8 个写接口 + `hot.py:157` 聚簇 + `hot.py:273` 日报）对 operator 返回非 10004，对 user 返回 10004，对 admin 不变。

## 1. 辩证（为什么不是"把 max 改成 min"）
- **支持改 min**：`roles.py` 模块 docstring 写「任一请求角色达标即放行」，调用方写两个参数的意图明显是 operator+。
- **反对改 min（采纳）**：冻结 identity 契约 `docs/任务规划V0.12.0/contracts/identity.schema.json:31` 明写「`require_roles(*roles)` 取所需角色的**最高** rank」——代码与契约一致，错的是 docstring 和调用点。改 min = 改冻结契约语义 + 让未来任何多参数调用的含义翻转。
- **裁决 D-V11-01**：保留 max 契约；`_required_rank` 对 `len(roles) > 1` fail fast；10 个调用点按意图改为 `require_roles("operator")`。单参数下 max 与 min 等价，契约文本无需改动。
- **代价（必须写进 EVD）**：operator 获得推送渠道建/改/删、测试推送、任务建/改/删/执行，以及热点聚簇、日报生成。operator 今天已能读到渠道明文凭据（D-V10-07），写权不扩大凭据暴露面。

## 2. 原子任务

### S25.1 先红
- [ ] **S25.1.1** 结构守卫 `apps/api/tests/test_require_roles_single_arg.py`（AST，不用正则）：遍历 `apps/api/app/**/*.py` 中 `require_roles(` 调用，实参数 ≠ 1 即红并点名文件:行；改前必须点名恰好 10 处（bots 8 + hot 2）
  - S25.1.1.a 自检：喂一段含 `require_roles("a","b")` 的合成源码 ⇒ 必须红
- [ ] **S25.1.2** 连库秩矩阵 `apps/api/tests/test_push_and_hot_rank_matrix.py`：10 个端点 × {user, operator, admin}
  - S25.1.2.a 判据只看是否 10004：user ⇒ 10004；operator/admin ⇒ 不为 10004（允许 404/422 等业务码，不要求 200，避免和业务前置耦合）
  - S25.1.2.b 改前 operator 列 10 格全红（原文入 EVD）

### S25.2 修复
- [ ] **S25.2.1** `apps/api/app/api/v1/bots.py` 8 处、`apps/api/app/api/v1/hot.py` 2 处 ⇒ `require_roles("operator")`；删除 `bots.py` 里那条"不要抄成两个参数"的说明注释（守卫已经把它变成机器约束）
- [ ] **S25.2.2** `apps/api/app/services/roles.py`
  - S25.2.2.a `_required_rank`：`len(roles) > 1` ⇒ `ValueError("require_roles 只接受一个最低角色……")`
  - S25.2.2.b 模块 docstring 改为与契约一致（"所需角色即最低秩；需要 operator+ 时写 operator"）
- [ ] **S25.2.3** `apps/api/tests/test_idor_matrix.py` 的基数锚若因调用点形态变化而变：只更新数字并在 EVD 写明 before/after 和原因；**不得**删除断言

### S25.3 证据与对外文本
- [ ] **S25.3.1** EVD `docs/06_validation/evidence/EVD-V14-25/s25_readings.md`：两份先红原文、改后绿、复跑探针 ① 三行（期望 GET 200 / POST 非 10004 / PUT 非 10004），并附 `@ci` run id（`head_sha` 校验）

## 3. 验收标准
- [ ] `git grep -nE 'require_roles\("[a-z]+", *"' apps/api/app` = 0
- [ ] S25.1.1、S25.1.2 改前红、改后绿，EVD 有原文
- [ ] `has_min_rank("operator","admin","operator")` 抛 ValueError（不再静默返回 False）
- [ ] 全量 0 failed；CI / CI-Windows / Security 三绿；Windows skip 基线若因新增连库用例而变，按 D-V10-11 程序重测

## 4. 验证命令
```bash
cd apps/api && python -m pytest tests/test_require_roles_single_arg.py tests/test_push_and_hot_rank_matrix.py tests/test_idor_matrix.py -q
git grep -nE 'require_roles\("[a-z]+", *"' apps/api/app || echo "0 hits"
python -c "from app.services.roles import has_min_rank; has_min_rank('operator','admin','operator')"  # 期望 ValueError
```

## 5. 允许修改
- `apps/api/app/services/roles.py`、`apps/api/app/api/v1/bots.py`（仅 `Depends(require_roles(...))` 实参与相关注释）、`apps/api/app/api/v1/hot.py`（同上）
- `apps/api/tests/test_require_roles_single_arg.py`、`apps/api/tests/test_push_and_hot_rank_matrix.py`（新建）、`apps/api/tests/test_idor_matrix.py`（仅基数锚）
- `.github/workflows/ci-windows.yml`（仅 skip 基线数字，按 D-V10-11 程序）
- `docs/06_validation/evidence/EVD-V14-25/**`

## 6. 禁止修改
- `docs/任务规划V0.12.0/contracts/**`、`packages/contracts/**`
- `bots.py` 中 `create_push_task` 函数体（STEP-24 所有）
- `apps/web/**`（按秩隐藏入口属 STEP-15b 的 P-21 增量）

## 7. 依赖与阻塞
- Depends on：STEP-24（矩阵里的 `POST /bots/tasks` 需要先不再 500，否则 operator 格无法区分 10004 与 50001）
- Blocks：STEP-21（IDOR 矩阵按单参数秩写）、STEP-26、STEP-15b
- 阻塞条件：发现第 11 个多参数调用点且意图不明 ⇒ 停，登记 P-xx，交规划方裁决

## 8. 熔断
同 D-14：同一判据连续 2 次 FAIL ⇒ 停止改代码。
