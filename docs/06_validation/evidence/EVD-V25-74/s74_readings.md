# EVD-V25-74 读数：`admin.spec.ts` ⑥ 定位器收窄（P-158）

> 卡面：`docs/任务规划V0.25.0/steps/STEP-74-admin⑥定位器.md`
> 本文件只记读数与反证；判词在 `07-执行过程记录.md`。

## 1. 先红（S74.1）：现场未漂移

| 项 | 值 |
|---|---|
| 来源 | `docs/06_validation/evidence/EVD-V23-67/s67_7_test6_error.txt`（原文逐字保留，未改） |
| run / sha | `40668413325` @ `3c4138d`（STEP-67 第 2 轮） |
| 失败位置 | `at /home/runner/work/BotHot/BotHot/apps/web/e2e/admin.spec.ts:271:50` |
| 失败形 | `Error: strict mode violation: getByRole('status').getByText(/告警\|依赖未就绪\|未知/) resolved to 2 elements:` |
| 命中 1 | `<span data-tone="degraded" …>告警未启用</span> aka getByText('告警未启用')` |
| 命中 2 | `<p class="min-w-0 flex-1 basis-48 …">依赖就绪，但告警探测器未启用（ALERTING_ENABLED=false）：…</p> aka getByText('依赖就绪，但告警探测器未启用（')` |
| 该 run 的 `/ready` | `HTTP 200 … "alerting":"disabled"`（同一份日志第 5 行）⇒ 真档落在「告警未启用」态 |

**漂移检查**（S74.1 的「若现场已漂移 ⇒ 停手」）：

```
$ git diff --stat 3c4138d..HEAD -- apps/web/e2e/admin.spec.ts apps/web/components/admin/AlertBanner.tsx
（空）
```

⇒ 断言所在文件与产品组件自 `3c4138d` 起零改动，先红仍描述当前字节，S74.1 通过，不必补新读数。

## 2. 改动（S74.2 / S74.3 / S74.4）

`git diff --stat`：`apps/web/e2e/admin.spec.ts | 2 +-`（1 行，`+1/-1`）。原文见 `s74_before_after.txt`。

| 行 | 改前 | 改后 |
|---|---|---|
| `:271` | `bar.getByText(/告警\|依赖未就绪\|未知/)` | `bar.getByText(/告警未启用\|告警已启用\|依赖未就绪\|未知/)`（与 `:268` 逐字同串） |

未用 `.first()`、未用 `{ exact: true }`、未动 `:268`、未动产品侧。

## 3. 反向验证（S74.5）

**本机不能跑真档**：`real` project 需要 `E2E_REAL_BACKEND=1` + :3300 后端（PG + Redis + 迁移）+ :3200 的 `next build`；本机无 Redis、无 docker CLI（口径与 `05` §3 一致）。按卡 §11 的阻塞条件，本机不实跑该用例，只贴读数 + 下条引擎级复算。

**替代反证（Playwright 引擎 + 逐字 DOM）**：用 `@playwright/test` 的 chromium 复算四种状态的命中数。DOM 结构与文案取自 `apps/web/components/admin/AlertBanner.tsx:91-106`（`section[role=status]` 内含 StatusPill 的 `span`、说明段 `p`、重读 `button`）；探针脚本在仓外（`D:\Code\tmp_s74_locator_probe.cjs`），不入库。

| 状态 | 宽式 `/告警\|依赖未就绪\|未知/` | 窄式 `/告警未启用\|告警已启用\|依赖未就绪\|未知/` | 结论 |
|---|---|---|---|
| `disabled`（真档实测态） | **2** | **1** | 宽红窄绿 |
| `enabled` | **2** | **1** | 宽红窄绿 |
| `notready` | 1 | 1 | 两式皆绿（`p` 里是「依赖未就绪」，`span` 是「未就绪」，窄式只命中 `p`） |
| `unreadable` | **2** | **2** | **窄式仍双命中**（见 §5） |

⇒ 「宽式状态下该用例红」有两条独立证据：① CI 原文（`40668413325`，退出码 1）；② 引擎级复算（`disabled` 态宽式 2 命中 = strict mode 的前置条件）。

## 4. 本机静态核对

```
$ grep -c "告警未启用|告警已启用|依赖未就绪|未知" apps/web/e2e/admin.spec.ts
2
$ grep -n "告警未启用|告警已启用|依赖未就绪|未知" apps/web/e2e/admin.spec.ts
268:      await expect(bar.getByText(/告警未启用|告警已启用|依赖未就绪|未知/)).toBeVisible();
271:      await expect(bar.getByText(/告警未启用|告警已启用|依赖未就绪|未知/)).toBeVisible();
$ grep -c "first()" apps/web/e2e/admin.spec.ts
1
$ grep -n "first()" apps/web/e2e/admin.spec.ts
253:      await expect(page.getByRole("button", { name: "登记" }).first()).toBeVisible();
```

- 逐字同串出现 2 次：`:268` 与 `:271`（S74 的验收判据 = 2）。
- `.first()` 本文件现有 1 处，是 **`:253` 的 ⑤（D-V24-08 追认的 `3c4138d` 既有字节）**，本卡贡献 **0**；`git diff` 里没有 `.first()`。
- `git diff --stat` 只含 `admin.spec.ts` 一行 + 本证据目录。

## 5. 观察项（交回规划方，本卡不改）

窄式在 **`unreadable` 态**（`/ready` 读不到 ⇒ `AlertBanner` 画「未知」）仍会 2 命中：`span` 是「未知」，说明段里含「按未知处理」。真档 `e2e-real` 的 `/ready` 是 200（先红日志第 5 行），不会落到该态，故本卡不改；但它意味着**一旦真档探针不可读，⑥ 会以同一种 strict-mode 失败回来**。

产品侧双渲染是**刻意事实**：`AlertBanner.tsx:97-98` 并排渲染 `StatusPill`（章）与 `p`（说明段），两者都含状态词——这正是 `.first()` 被禁的原因（`03` §2.1）。⇒ 按卡 §6 最后一条，向 `04` §8 补一条观察项：`04` §8 现读指向 `05` §4.1 的 **O-1**（内容只在 `05` 存一份，避免两处各写一版）。

## 6. @ci 读数（S74.7 / S74.8）

原文见 `s74_ci.txt`（head `299b220`，CI run `40692846396`）。

| 项 | 改动前（`a1ef93a`） | 本卡提交后（`299b220`） |
|---|---|---|
| `E2E (real backend, project=real, admin.spec.ts)` | `failure` | **`success`** |
| ⑥ | `✘` strict mode 2 命中 | **`✓` 476ms** |
| ⑦ | `did not run` | **`✓` 403ms** |
| 计数 | `1 failed / 1 skipped / 1 did not run / 4 passed` | `6 passed / 1 skipped` |
| `e2e-real` job | `failure` | **`success`** |
| `Stop stack` | `success` | `success` |

⇒ 卡面 §6 的两条 @ci 判据（⑥ 通过、⑦ 出现）都满足；`.first()` 未使用（`grep -c` 仍为 `:253` 那一处，本卡 +0）。

