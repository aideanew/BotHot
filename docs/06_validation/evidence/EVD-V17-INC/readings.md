# EVD-V17-INC · V0.17 增量补完批（S15.V17.1 + S15b.V17.1）

> 这批不是新卡，是**两张已收口卡的 V0.17 增量漏判补完**。
> 增量表：`docs/任务规划V0.17.0/steps/STEP-继承卡增量-V0.17.md` 第 9、10 行。
> 基线：STEP-15 收口 `6a6525f`（三绿）+ STEP-14b 交付 `4b8c1ee`。

## 1. 为什么会有一批"补完"：收口判定漏了增量表（自曝）

STEP-15 的收口判定（`EVD-V13-15/readings.md` §1）是**按 V0.13.0 卡面字段 8 的三级任务逐条现读**做的，
九条全判了；但 V0.17 给这张卡另加了一行 `+1 项 S15.V17.1`，写在增量表里而不是卡面字段 8 里。
STEP-15b 同形（`+1 项 S15b.V17.1`，即 P-47）。于是出现了最难发现的那类漏判：
**收口判据本身是完整的，只是覆盖面少了一处**——九条都绿，第十条根本不在表上。

这不是代码缺陷，是流程缺陷，所以登记 **P-89**（"收口判定必须同时覆盖 V0.17 增量表的 +N 项"，
建议规划方把它做成一道门：卡面三级任务数 + 增量表该卡行数 = 判定行数，不等就红）。

## 2. S15.V17.1 —— 引擎不可用原因改读契约 `reason`

卡面要求：`EngineSwitcher`（及调用 `GET /engines` 的地方）按 `reason` 显示原因，
`not_allowlisted` → "未开放，请联系管理员"、`key_missing` → "未登记 API Key"、
`not_implemented` → "暂未接入"，`ok` 才可选；类型按 `packages/contracts/schemas/engine.schema.json` 写。

现读到的事实（改之前）：

| 消费面 | 改之前在做什么 | 后果 |
|---|---|---|
| `components/EngineSwitcher.tsx` | 从 `allowlisted`/`configured`/`implemented` 三个布尔自己推顺序 | 推出来的顺序与后端那份不是一份，两处会分家 |
| `app/engines/page.tsx` | **先判 `configured` 再判 `allowlisted`** | "既没开名单也没配 Key"的引擎显示"未配置 Key"，把管理员指到一个解决不了的处置上（该去开名单，被引导去配 Key） |
| `components/onboarding/StepPanels.tsx` | 任何不可用一律标"（未配置）" | 三种处置人不同的故障在界面上同形 |
| `lib/api/engines.ts` | `EngineItem` **根本没有 `reason` 字段** | STEP-13 交付的契约字段在前端无人消费——`grep -rn "reason" lib/api/engines.ts` 改前 0 命中 |

改之后：`EngineReason` 联合与两张表（`ENGINE_REASON_TEXT` / `ENGINE_REASON_LABEL`）落在
`lib/api/engines.ts`（唯一源），`reason` 在 `EngineItem` 上是 **required**（契约里就是 required，
CI 有 `gen_contracts --check` 漂移门兜后端），三个消费面一律只读 `reason`，不再自己推。
可选性也改判 `e.reason === "ok"`（契约不变量 `available === (reason === "ok")` 由后端单点保证）。

**顺带抓到的一处措辞分歧**：后端 `apps/api/app/api/v1/engines.py:61-65` 的 `REFUSAL_MARKERS` 是
"未开放 / **未配置** API Key / **尚未**实接"，卡面给前端的三句是
"未开放，请联系管理员 / **未登记** API Key / **暂未**接入"。同一 reason 在列表与切换拒绝里
读起来是两套词。本批按卡面画前端（那是判据来源），不改后端文案（那是 STEP-13 的所有权面）⇒ **P-90**。

## 3. S15b.V17.1（P-47）—— 引擎密钥面板按角色收写面

后端事实：`GET /admin/engines/keys` 是 `require_roles("operator")`，
`POST`/`DELETE /admin/engines/keys/{engine}` 是 `require_roles("admin")`。
所以 operator 能读不能写，而面板原先把"登记 / 轮换 / 停用"三个写入口对所有人画出来。

改后：`canWrite = me?.is_admin === true`；非 admin 时三个按钮全部不渲染，改画一行"只读 + 该找谁"。
判据是卡面点名的两条 vitest（两个角色各一条），落在 `tests/admin-ops-panels.spec.tsx`。

**这一条今天不是用户可见的修复，写清楚**：`/admin/ops` 的页面门本身就判 `me.is_admin`，
operator 今天根本进不到这一屏。所以它是**纵深防御**——面板被嵌进别的门、或页面门哪天按后端
放宽到 operator 时，写面不会跟着漏。把它说成"修好了 operator 看到假按钮"就是造假。

顺带修掉同一文件里一句**与门不符的话**：`/admin/ops` 的"权限不足"卡原先写
"运维台需要 operator 以上角色（后端 `require_roles("operator")`）"，而代码判的是 admin。
按 D-V3-06（沿用 admin，不新增 RBAC）留门、改文案，并把"页面门比后端严是安全的一侧，反过来才是洞"
写在文案里——放宽访问面不是本批该做的事。

## 4. 读数

| 项 | 读数 |
|---|---|
| `pnpm run test:unit` | **49 files / 410 tests**，0 failed（本批 +4：reason 口径 2 条 + 角色门 2 条） |
| `pnpm exec tsc --noEmit` | 0 错。`reason` 改 required 后 tsc 抓到 4 处缺字段的 fixture（`engines.spec.ts` 2、`r062-onboarding-steps.spec.tsx` 2）——**这就是把契约字段设为 required 的回报**：漏消费会被类型门拦住，不再靠人眼 |
| `pnpm run lint` | `✔ No ESLint warnings or errors`（rc=0） |
| `NEXT_PUBLIC_API_MOCK=true pnpm exec next build` | rc=0 |
| `NEXT_PUBLIC_API_MOCK=false pnpm run build` | rc=0，`/admin/ops 8.18 kB / 126 kB`、`/engines 3.81 kB / 122 kB` |
| mock 产物 e2e | **31 passed / 11 skipped / 0 failed**（rc=0） |

两条过程读数，比结果更值得记：

1. **lint 红过一次，而它差点被当成"只是 lint"**：新文案里用了 ASCII 双引号，
   `react/no-unescaped-entities` 报错，而 **`next build` 会跑同一套 ESLint 并因此失败**——
   第一次跑链条时 `pnpm run lint | tail` 把退出码吃掉了，看起来"编译成功"，
   紧接着 e2e 报 `Could not find a production build in '.next'`。真实顺序是构建被 lint 门拦下。
   已改成取 `$?` 的写法复跑，两档构建各自 rc=0。
2. **两个 spec 的 `vi.mock("@/lib/api")` 在组件扩面时静默崩**：`EngineSwitcher` / `StepPanels`
   一旦开始读 `ENGINE_REASON_*`，手写"最小可用面"的 mock 工厂就让组件拿到 `undefined`，
   10 条用例同时红。改成 `importOriginal` 展开真实模块 + 只覆盖两个域函数。
   这与 P-84/P-85 同族：**判据测的是我自己声明的那个面，不是组件真正依赖的面**。

## 5. 反证

把 `ENGINE_REASON_TEXT.key_missing` 从"未登记 API Key"改成旧文案"未配置 API Key"
⇒ `engine-switcher-states.spec.tsx` **2 条红**（卡面口径那条 + 分层优先级那条），
改回后 6/6 绿。这条反证的作用是：判据锁的是**卡面那三句字**，不是"有没有一句话"。

## 6. 本批没做的

- STEP-14b 增量句里的另一半「**采集配置页**」（`/admin/categories`、`/admin/article-fallback`
  两组端点目前前端 0 消费）不在本批，随后一批做。渠道启停已在 `4b8c1ee`。
- `SKIP_BASELINE_WIN` 保持 **653**：本批零 `apps/api/**` 改动、零 pytest 新增。
