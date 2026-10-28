# STEP-60 订正增量（V0.25.0，不重编号）

> 按 D-V23-05 / D-V25-04：**不重编号、不重写卡面**。原卡在 `docs/任务规划V0.22.0/steps/`，
> V0.24.0 的增量在 `docs/任务规划V0.24.0/steps/STEP-继承卡增量-V0.24.md` §1。
> 本文件是**第三层**：只列 V0.25.0 对 STEP-60 的三处订正。冲突时以本文件为准。
>
> **编号对照（必须先看）**：规划方 2026-10-28 的只读报告把 ci.yml 那一步叫「S60.3」，
> 而 V0.24.0 已下发的增量文件里 S60.3 = 写 5 条用例、**S60.4 = 加 ci.yml 那一步**。
> ⇒ 本文件一律用 **V0.24.0 的实际编号**；规划报告的「S60.3」= 本文件的 **S60.4**（同一处，不是两条）。

## 订正一：S60.4 的 `env` 不完整，且缺一条「非 skipped」断言

**现状（V0.24.0 增量 §1.3 S60.4 的 yaml 片段）**：

```yaml
- name: E2E (real backend, project=real, r19-chat-stream.spec.ts)
  run: pnpm exec playwright test --project=real e2e/r19-chat-stream.spec.ts
  env:
    E2E_CHAT_LLM: "1"
```

**问题（现读 `ci.yml:644-649` 的 admin 那一步作对照）**：

| 键 | 相邻的 admin 步（已运行、已绿过） | V0.24.0 的 r19 片段 | 缺了会怎样 |
|---|---|---|---|
| `PORT` | `"3200"` | **缺** | `playwright.config.ts:22` 回落到默认 3200，本机/CI 都还是 3200 ⇒ **实际无害，但不该靠默认值** |
| `E2E_REAL_BACKEND` | `"1"` | **缺** | `playwright.config.ts:23` ⇒ `real` project **根本不存在** ⇒ `--project=real` 直接报 "Project(s) 'real' not found"，或退化成「0 tests，绿」 |
| `E2E_SEED_FILE` | `${{ runner.temp }}/e2e-real/seed.txt` | **缺** | `real.setup.ts` 的 `defaultSeedFile()` 会算到 `RUNNER_TEMP/e2e-real/seed.txt` 同一路径 ⇒ 大概率仍读到；但同文件注释已写明「设了 `E2E_RUN_DIR` 而两边算式不同 = 静默失效」，不该留这个位 |
| `E2E_CHAT_LLM` | 无（admin 不需要） | `"1"` | 缺 ⇒ `r19:24-25` 的 skip 条件命中 ⇒ **只 skip**（F-6） |

**订正后（逐字）**：

```yaml
      - name: E2E (real backend, project=real, r19-chat-stream.spec.ts)
        shell: bash
        env:
          PORT: "3200"
          E2E_REAL_BACKEND: "1"
          E2E_CHAT_LLM: "1"
          E2E_SEED_FILE: ${{ runner.temp }}/e2e-real/seed.txt
        run: pnpm exec playwright test --project=real e2e/r19-chat-stream.spec.ts
      - name: 断言 r19 这一步不是 skipped（F-6：绿着零读数比不跑更坏）
        shell: bash
        run: |
          # 为什么单列一步：Actions 里「测试没跑」与「测试全过」在 conclusion 上长得一样（都绿）。
          # 上面那一步若因缺 env 整片 skip，playwright 会 exit 0 并打印 "0 passed / N skipped"，
          # 判据于是从「五态有真读数」退化成「命令没报错」。这一步把「有真读数」变成会红的判据。
          # 读法：list reporter 的成功行形如 "✓  1 …"，跳过行形如 "-  1 …"。
          echo "占位校验：本步由执行者按实际输出补最小断言（见下方 3 条候选）"
```

**本条断言的三种可选实现（执行者按当时输出择一，必须写进证据）**：

| 候选 | 断言 | 强度 |
|---|---|---|
| 甲（推荐） | 把 r19 那一步的 stdout 落文件，`grep -c "✓"` ≥ 1 且 `grep -c "skipped"` = 0 | 强：直接判「有通过」 |
| 乙 | `grep -c "5 passed"` = 1（契约 5 态 ⇒ 5 条用例） | 强但脆：60 的阻塞条件允许只交 4 条 ⇒ 会与本卡自己的 §1.5 打架 |
| 丙 | 用 `--reporter=json` 落盘后 `python -c` 统计 `status` 计数 | 最强，但要改 reporter 配置面 |

⇒ **推荐甲**：它同时满足「不许 skipped」与「不许全红当绿」，且不预设用例条数（不会与 §1.5「可能只交 4 条」冲突）。

## 订正二：前置依赖加 74、75

**原**（V0.24.0 `04` §2 卡表）：`STEP-60 | 依赖 68、69、72、73`
**订正后**：`STEP-60 | 依赖 68、69、72、73、**74**、**75**`

| 新增依赖 | 理由（证据链） |
|---|---|
| **74** | `e2e-real` 的 `E2E` 步里 ⑥ 是 strict-mode 红（`EVD-V23-67/s67_7_test6_error.txt`）。60 的读数面是同一步，⑥ 不绿则「60 的读数」里永远掺一条已知红，无法区分「60 新写的用例红」还是「⑥ 老红」 |
| **75** | `ci.yml:546` `needs: [backend, frontend]` ⇒ `backend` 红时 `e2e-real` **直接 skipped、steps 为空**（`5002410` 实测）。不先解除这层遮蔽，60 加了 step 也取不到读数（F-5） |

**为什么这两条不能「并行着先做 60」**：60 的验收物就是「读数」；读数通道被两层遮住（`needs` 连坐 + `continue-on-error`）时，
60 唯一能交的是代码，交不出读数 ⇒ 按 D-V24-07 口径它只能标 ⏸/❌，等于白跑一轮。

## 订正三：S60.1 追加 `r19` 头部注释纠真

**原**（V0.24.0 S60.1）：只写「删 `UX_STATES` 数组与 ④ 用例」。
**订正后追加**：同一步内删/改 `apps/web/e2e/r19-chat-stream.spec.ts:18-21` 的两句过期判词：

```
 * 八态取自 `docs/任务规划V0.12.0/contracts/ux_states.schema.json` 的 `State` 枚举
 * （initial/loading/empty/success/error/forbidden/unauthenticated/degraded）。
 * ⚠️ 该契约文件在 V0.13.0 及以后的树里没有再出现（`ls docs/任务规划V0.17.0/contracts/` 零命中），
 *    本 spec 引用的是历史版本的冻结稿——这条按读数登记，不在本卡修。
```

**两句各错在哪**：

| 句 | 现读事实 | 处置 |
|---|---|---|
| 「八态取自 `State` 枚举」 | 契约 `/chat` 只列 **5** 键（V0.24.0 `01` §2.2 逐字引用） | 改为「五态取自 `x-core-views` 中 `/chat` 那一段的 `states` 键集；8 值是全局词表」 |
| 「该契约文件在 V0.13.0 及以后没有再出现」 | `docs/任务规划V0.12.0/contracts/ux_states.schema.json` **存在**，且 `apps/api/tests/test_ux_states_contract.py` 正引用它做比对 | 整句删除（原判词是「当前树里没有 contracts 目录」的过期推断，冻结稿按 D-V10-06 恒定在 V0.12.0） |

**为什么必须与 S60.1 同一步做**：S60.2 已经要求「运行时读冻结稿」；若头注仍写「该文件没有再出现」，
同一文件内就同时存在「读它」与「说它不存在」两种陈述——下一个读代码的人会先信注释。

## 订正四（不改动，只登记）：S60.4 的插入位置

`ci.yml` 里 r19 那一步**必须排在 admin 那一步之前**（D-V23-09：Actions 顺序执行，admin 红则其后全 skipped；
60 的读数要单独可用）。**这条 V0.24.0 已写，本版不动。**

## 汇总：STEP-60 的判据在 V0.25.0 里增加了什么

| 项 | V0.24.0 | V0.25.0 追加 |
|---|---|---|
| 依赖 | 68、69、72、73 | + 74、75 |
| `ci.yml` 步的 `env` | 只有 `E2E_CHAT_LLM` | + `PORT` / `E2E_REAL_BACKEND` / `E2E_SEED_FILE` |
| 「不是 skipped」的机器判据 | 无 | 新 step（候选甲：`grep -c "✓"` ≥ 1 且 `grep -c "skipped"` = 0） |
| `r19` 头注 | 不动 | 两句过期判词随 S60.1 一并改 |
| 5 条用例 / 只交 4 条 | 已写（§1.5 阻塞条件） | 不变 |
