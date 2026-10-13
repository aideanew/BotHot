# STEP-00R 测试基线收口残项

| 项 | 值 |
|---|---|
| 里程碑 | M1（并行支线） |
| 档位 | sonnet |
| 规模 | 小（约 0.5 人日；S0R.3.1 需 docker 执行者） |
| 依赖 | STEP-00C；D-11 |
| 裁决 | D-11 |
| 剩余原子任务 | 3（👤 1） |
| 所有权（写） | W：scripts/test-env.sh（只验证）、.github/workflows/ci.yml:28-32（注释）、Makefile（evidence-check CI 化） |
| 基线 | main@65f508b |

## 1. 目标与可证伪验收
- `scripts/test-env.sh up/down` 在有 docker 或本地 PG/Redis 的机器上实跑通过（STEP-00 遗留未跑分支）。
- ci.yml 注释与 conftest 实际行为一致（两级解析 + 拒连广播）。
- evidence-check 以 stdlib job 进入 CI（授权范围内）。

## 2. 证据链（现状）
- V0.4.0 执行账：00R 剩 S0R.3.1、S0R.3.3、S0R.4.1(CI 部分)。
- conftest.py:56-64 两级解析、:75 无条件广播；ci.yml:28-32 注释仍描述旧三级回退。

## 3. 执行逻辑穿透
test-env.sh up → PG16:5547 + Redis → 导出 AIDEANBOT_TEST_PG_DSN → pytest；down → 端口释放。Redis 可用后 3 条 Redis skip 消失，skip 进一步降到 2（仅 LangBot）。

## 4. 原子任务（三级编号；缩进为四级执行步）

标记：🔴 先红（写失败测试）｜🛠 实现｜✅ 验证/读数｜📄 文档｜🗄 数据/迁移｜👤 人工/裁决

### S0R.3 环境脚本与 CI 注释
- **S0R.3.1** 👤🗄 有 docker 的执行者实跑 `test-env.sh up` → `psql select 1` → 全量 pytest → `down` 后端口释放
  - S0R.3.1.1 记录 Redis 可用时 skip 数（预期 2）
- **S0R.3.3** 📄 ci.yml:28-32 注释更正为两级解析 + 拒连广播，不改行为

### S0R.4 证据门禁进 CI
- **S0R.4.1** 🛠 ci.yml 新增 stdlib job `evidence-check`（不装依赖，只跑 Makefile 目标的 stdlib 部分）
  - S0R.4.1.1 本地 `act` 或等价命令验证 job 语法（actionlint 已在 workflow-lint）

## 5. 测试设计
- 无新增用例。

## 6. 停止条件与回滚
- 无 docker 执行者：S0R.3.1 标 blocked（外部资源），不阻塞 M1。

## 7. 交付证据
EVD-V2-00R（追加）：up/down 读数、新 job run id。

## 8. 完成定义（本卡）
所有权内 diff 与任务一致 ∧ 每个 ✅ 有读数 ∧ 本地 `ruff check app tests`（0.12.12）与 `gitleaks detect` 通过 ∧ 推送后 CI 与 Security 均 success（run id 入 EVD）∧ 复审 ≤2 轮（D-14）。
