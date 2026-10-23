# STEP 继承卡增量（V0.19.0）

STEP-34～37 卡面仍在 `docs/任务规划V0.18.0/steps/`；下表是本版对它们的**加项**。收口判定必须覆盖卡面三级任务 + 本表加项（D-V18-15）。STEP-18 无新加项（V0.18.0 增量仍有效）。

> 状态（执行助手现读）：S34.7 / S34.8 已随 STEP-34 第 1 轮交付（2026-10-24，读数在 `docs/06_validation/evidence/EVD-V18-34/`）；S35.5 已随 STEP-35 交付；S37.5 已随 STEP-37 第 1 轮交付（2026-10-24，读数在 EVD-V18-37 §S37.5）。

| 卡 | 加项 | 内容 | 来源 | 判据 | 允许面增量 | 规模 |
|---|---|---|---|---|---|---|
| STEP-34 | **+S34.7** | 掩码守卫的"已生成 / 已掩码"两个集合改为 job 级；`GITHUB_OUTPUT` 与 `GITHUB_ENV` 同等对待；全仓零可检面 ⇒ rc=3 | P-109 / D-V19-05 | 新增跨步反证：上一步生成未掩码、下一步写 GITHUB_ENV ⇒ 红；上一步已掩码 ⇒ 绿；`test_mask_in_an_earlier_step_of_the_same_job_covers_the_write` 仍绿 | `scripts/guards.py` 的 `ci_mask_violations`、`apps/api/tests/test_guards_ci_secret_mask.py` | 0.2 人日 |
| STEP-34 | **+S34.8** | 先清 `mypy scripts/guards.py` 的 3 条 error，再把 `ruff check ../../scripts` 与 `mypy ../../scripts` 加进 `ci.yml`、`ci-windows.yml` 的 lint/type 步与 `entry.py` 的 `lint-backend` | P-110 / D-V19-06 | 清零后再扩门；扩门那一提交本机与 @ci 都绿；故意在 scripts 里放一个未用 import ⇒ lint 红（反证后还原） | `scripts/**`（只修类型/格式，不改判据语义）、两处工作流 lint/type 步各加一行、`scripts/entry.py` 的 `lint-backend` 一处 | 0.2 人日 |
| STEP-35 | **+S35.5** | 常驻用例：未认证 + 非法体（夹带运行时随机值）打三个真端点 ⇒ 401/10001，随机值不在响应体与日志里；注释写明"绿是因为鉴权在校验之前" | P-111② / D-V19-08 | 新用例在 9c66add 上就绿（这是行为固定用例，不要求先红；证据写明这一点） | `apps/api/tests/test_validation_no_echo.py` | 0.1 人日 |
| STEP-37 | **+S37.5** | `ResourceNotFoundError` 的 message 改固定文案（"资源不存在或无权限"），不再拼调用方给的 id；同步改 `bots.py` 等 13 处 `raise ResourceNotFoundError(f"…{id}")` 的文案为不带 id；`test_envelope.py:123` 的断言随改 | P-111① / D-V19-07 | 先红：往 `task_id` 塞运行时随机值打 404 端点 ⇒ 值出现在响应 message；改后不出现；前端没有任何地方解析这段 message（`grep` 读数入证） | `app/core/errors.py` 的 `ResourceNotFoundError`、13 处 raise 的字符串字面量、`tests/test_envelope.py` | 0.3 人日 |
