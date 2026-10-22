# EVD-V13-15 · STEP-15 收口判定（前端契约层与真实后端对齐）

> 卡面：`docs/任务规划V0.13.0/steps/STEP-15-前端契约层与真实后端对齐.md`
> （字段 8 的三级任务 + 卡片自带的 V0.11.0 执行记录）。本文件是**收口判定**，不是第二次实现。
> 收口基线 `99a210a`（STEP-15b 交付完成后）。
> 卡面字段 11 的证据路径 `docs/任务规划V0.8.0/evidence/61358c3-15/` 本仓从未建过（P-58/P-65 同形）
> ⇒ 按现行约定落本目录。
>
> 声明：本卡的所有锚都是现读的（`git diff --stat b2b76a6..HEAD -- apps/web` 为空 ⇒ 下表读数
> 可以直接算在 `b2b76a6` 那次实测上，没有"改完不重测"的空间）。

## 1. 逐条三级任务的现读判定

| 三级任务 | 判定 | 现读锚与事实 |
|---|---|---|
| S15.1.1 单一 fetch 封装 | **已确认（且早就在位）** | `lib/api/http.ts:113` 的 `request<T>()`：信封解包、`code!==0` → `ApiError`、401→10001、429→20005、错误码→文案（表在 `types.ts`，见 STEP-15b 的搬迁理由）。V0.11.0 记录写的 `http.ts:83-122` 已漂移到现在 113 起，**行号按 V0.13.0 卡面「禁止照抄来源卡读数」重锚** |
| S15.1.2 OpenAPI→TS 生成脚本 | **不做（裁定成立，且现在有第二份证据）** | `apps/web/package.json` 里没有 `gen:api` 脚本（`grep -n "gen:api" package.json` 零命中）；唯一源在位：`scripts/gen_contracts.py` + CI 的 `Contract drift gate (gen_contracts --check)`（`ci.yml:136-137`）与 `Contracts package strict check`（`ci.yml:334`）。再加一条 OpenAPI→TS 管线就是第二份真相（违反 D-09），**这条不是"没做完"，是不该做** |
| S15.1.3 分页 hook `usePaged<T>` | **已确认** | `lib/hooks/usePagedList.ts` 在位，且被 `tests/w9-paged-list.spec.ts` / `tests/w9-pagination.spec.ts` 覆盖 |
| S15.2.1 四个 hook 改用客户端 | **已确认** | `grep -c 'from "@/lib/api"' components/use*.ts` = **4**（`useAdminData` / `useJobsList` / `useSpaceDetail` / `useSubscriptions`，正好是卡面点名的四个） |
| S15.2.2 删除 mock 分支与死代码 | **已确认（由 STEP-15b 交付，本卡复验）** | `grep -rn MOCK_ENABLED lib/api \| wc -l` = **1**（V0.11.0 记录时是 39）。剩下那 1 处是 `index.ts:31` 的别名转出，不是判定点。豁免清单与未登记抛错的形状见 EVD-V13-15b §3 |
| S15.2.3 admin 6 组端点各一个 typed 函数 | **已确认** | `lib/api/admin-ops.ts` 七个 typed 函数在位，从 barrel 转出 |
| S15.3.1 单测覆盖解包/错误映射/分页 | **已确认** | `tests/admin-ops-api.spec.ts` + 既有解包/错误映射覆盖；STEP-15b 又补了 14 条（默认值三态 + 统一表判据） |
| S15.3.2 typecheck + lint 0 错 | **已确认** | `tsc --noEmit` 0 错、`next lint` 无告警、`test:unit` 49 files / 399 tests、`NEXT_PUBLIC_API_MOCK=false pnpm build` 成功（都是 STEP-15b 交付批次里跑的，`apps/web` 自 `b2b76a6` 起未再改动） |
| S15.3.3 e2e 冒烟（对真后端） | **证据不足（环境阻塞，非缺件）** | 与 STEP-15b 的 S15b.3.1 同一个阻塞：本机无 Playwright 浏览器二进制、无主平台 OIDC 白名单。通路级读数已取到（见 EVD-V13-15b §4）。登记在 **P-83**，本卡不重复计件 |

## 2. 目标句的口径修正（这条是本卡真正的产出）

卡面目标写的是：「apps/web **所有** API 调用经同一契约客户端；类型由 OpenAPI 生成；去掉残留 mock 分支。」
两句要按现读改口径，否则下一个读卡片的人会去找一条不存在的统一：

1. **「所有 API 调用」不成立，差两条，而且不该收。** 现读 `lib/` 里除 `http.ts` 外只有两处自己碰传输层：
   `lib/api/ask.ts:80` 的 `fetch("/api/v1/chat/ask")`（要读 SSE 事件流，信封解包会把它吞成一次 JSON）
   与 `lib/api/notifications.ts:106` 的 `new EventSource(NOTIFICATIONS_ENDPOINT)`（长连接，不是请求-响应）。
   域函数侧的口径是清楚的：**75 处 `request(…)` / `request<…>(…)` 调用点**（`grep -rn "\brequest[(<]" lib/api
   --include=*.ts` 排除 `http.ts` 本体与 `mock-routes.ts` 内部两处 = 75，一函数一次：68 个 `export async function`
   + `admin-ops.ts` 的 7 个非 async 但返回 `Promise` 的 typed 函数），页面与组件里裸 `fetch(` **0 处**
   （`grep -rn "\bfetch(" apps/web/app apps/web/components | wc -l` = 0，这正是卡面「验收」那条）。
   所以正确的说法是"所有**信封**调用经同一客户端，流式两条各自持有自己的传输"，而不是"所有调用"。
2. **「类型由 OpenAPI 生成」这句与它自己的裁定冲突**（见 S15.1.2 行）：现行唯一源是
   Pydantic 内省 → `packages/contracts`，OpenAPI 生成是第二条真相。目标句留着这句话，
   就会诱使后来者"顺手补一个生成器"——那才是本仓最容易付出的代价（两套类型各有偏差时，红的那次总是别人）。

## 3. 判定汇总

| 项 | 档位 |
|---|---|
| S15.1.1 / S15.1.3 / S15.2.1 / S15.2.2 / S15.2.3 / S15.3.1 / S15.3.2 | **已确认**（S15.2.2 由 STEP-15b 交付、本卡复验） |
| S15.1.2 | **设计如此**（显式不做，D-09；卡面目标句需按 §2 改口径） |
| S15.3.3 | **证据不足**（环境阻塞；归 P-83，不在本卡修） |
| 页面裸 fetch | **0**（验收项达成） |

本卡**不新增代码**：`git diff --stat b2b76a6..HEAD -- apps/web` 为空，未触碰 `apps/api/**`、
未改 `apps/web/app/**` 布局（那是 14b 的所有权面）。产出是判定 + 那句目标口径的更正。

## 4. 三绿

本卡只改文档，验收提交待回填（`SKIP_BASELINE_WIN` 仍为 653：本卡零 pytest 新增）。

本地门的两条读数如实分开记：`scripts/check_docs_consistency.py` 23 个路径引用 / 0 个不存在；
`entry.py evidence-check` 在**尚未 `git add` 时返回 rc=3**——敏感形门的待检面取的是索引
（`guards.py:1075` 的 `secret_scope`），docs-only 批次索引为空时它按第三态报"这不是通过"，
`git add` 三个文档路径后复跑才 `✅ 全部通过（rc=0）` + gitleaks `344 commits scanned / no leaks found`。
这不是门的缺陷，是它的正确行为（空面不放行），但会把人误导成"文档批次过不了门"，
所以记一句：**先 add 再跑 evidence-check**。
