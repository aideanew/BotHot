# EVD-V13-14b · STEP-14b 收口读数（管理端四屏 UI 余项）

> 卡面：`docs/任务规划V0.13.0/steps/STEP-14b-管理端四屏UI设计与实现.md`
> 上一轮的执行记录在卡面字段 8 下方（V0.11.0 第二增量，@win 自验）。
> **本文件只记本轮做完的余项与改判**，不重述上一轮已经成立的四屏面板。
> 卡面字段 11 的证据路径 `docs/任务规划V0.8.0/evidence/61358c3-14b/` 本仓从未建过（与 P-58/P-65 同形）
> ⇒ 按现行约定落本目录。

## 1. 本轮的输入：上一轮留了三个 ❌/⚪

上一轮的记录里有三条不是"没做"，是**当时的前提不成立**：

| 三级任务 | 上一轮判定 | 前提现在的状态 |
|---|---|---|
| S14b.2.3 AlertBanner | ❌ 未做——"它属于 STEP-05 的读侧，先把那组端点定下来再画" | STEP-05（S5.1.1/S5.2.3）已交付静默告警；STEP-16 把 `ALERTING_ENABLED` 做成 `/ready` 上的可观测事实 ⇒ **前提已成立** |
| S14b.3.3 发现渠道"启停为只读" | ✅（范围已收窄）——"后端只有 GET，放个开关等于假装存在 PATCH" | STEP-28（D-V12-12）交付了 `PUT /admin/discovery/config` ⇒ **那句前提现在是假的**，留着只读就是把一个已存在的能力画没 |
| S14b.4.1 e2e 四屏主路径 | ⚪ 未跑——"本机无后端栈" | 本轮装上 Playwright 浏览器二进制（P-83 的那一半阻塞是环境，不是代码），取到了视觉读数；**但四屏在 CI 的阻塞档仍结构上不可达**（见 §5） |

所以本轮的交付面就是这三条 + 一处 375px 实测逼出来的修正。

## 2. 交付与越界声明（三处，全部显式）

卡面字段 12 只允许 `app/admin/**`、`components/admin/**`、`e2e/admin.spec.ts`。实际动了七个文件，
其中三处在禁止面里，逐条声明：

| 文件 | 改了什么 | 为什么必须动 |
|---|---|---|
| `lib/api/admin-ops.ts` | +`ReadyProbe`/`getReadyProbe()`、+`DiscoveryConfigResult`/`putDiscoveryConfig()` | 卡面字段 13 写"归 15"，而 STEP-15 已在本队列的紧邻前一张卡收口（`6a6525f` 三绿）；契约形状的唯一真源在 `lib/api`，把 `/ready` 的字段抄进组件就是造第二份真相（D-09 同族） |
| `lib/api/mock-routes.ts` | `MOCK_PASSTHROUGH` +1 条 `/api/v1/system/ready` | STEP-15b 的清单完整性判据扫 `lib/api/*.ts` 的每条字面路径，**新增路径必须命中表或命中豁免清单**，否则 `tests/mock-routes.spec.ts` 直接红。选豁免而不是造样例的理由写在清单里：`alerting` 是部署事实，给它编一份样例等于向运维宣布一个不存在的服务栈的状态 |
| `tests/admin-ops-panels.spec.tsx` | +7 条渲染契约 | 判据落点。上一轮同卡的 6 条渲染契约就在这个文件里（卡面字段 12 没列它，但字段 8 的 Done 需要可核对的判据） |

登记为 **P-87**（所有权矩阵覆盖不到"告警条要读哪个端点"这条链，交付必须越界），不在本卡修别人的卡面。

## 3. 读数（本轮全部现跑）

| 项 | 读数 |
|---|---|
| `pnpm run test:unit` | **49 files / 406 tests**，0 failed（STEP-15b 收口时 399 ⇒ 本卡 +7：AlertBanner 4 条 + 渠道启停 3 条） |
| `pnpm exec tsc --noEmit` | 0 错；`--listFiles` 里 `e2e/` 命中 **7** 个文件 ⇒ 新增的 `e2e/admin.spec.ts` 在类型门覆盖面上，不是漏检 |
| `pnpm run lint` | `✔ No ESLint warnings or errors` |
| `NEXT_PUBLIC_API_MOCK=false pnpm run build` | 成功。`/admin` **7.48 kB / first-load 130 kB**、`/admin/ops` **8 kB / 126 kB**（卡面 V0.11.0 记录是 6.88 kB / 123 kB，涨的是告警条 + 启停编辑器） |
| mock 产物 e2e（`NEXT_PUBLIC_API_MOCK=true` + `:3456`） | **31 passed / 11 skipped / 0 failed**，其中本卡新增 `e2e/admin.spec.ts` 无条件 4 条 + 闸门 3 条 |
| 前端消费数（卡面验收那条） | 六组里 **五组 ≥1**：`admin/engines/keys` 5、`admin/push/channels` 2、`admin/discovery/channels` 2、`admin/ops/liveness` 2、`admin/push` 1，本卡再加 `system/ready` 3；第六组 `auth/backchannel-logout` = **0**，见 §5 |

## 4. 视觉取证：口径先说清，再给图

P-83 当时记的是两件事：① 本机没有 Playwright 浏览器二进制；② 没有主平台 OIDC 白名单。
①本轮解除（`playwright install chromium`，195.6 MiB，走 10808 代理；直连那条路在
`cdn.playwright.dev` 上 10 分钟停在 0%）。**②没有解除**，所以：

- 这四张图**不是真后端读数**，是 `MOCK=false` 产物 + Playwright `page.route()` 拦截
  `/api/v1/**` 回填 fixture 信封的渲染取证。会话面靠 `middleware.ts` 的口径
  （它只查 `bothot_session` 的**存在**，"AuthGate 会做最终判定"）给一个占位 cookie 过关。
- 它证明的是：**组件在真实形状的回执下能画出来、画的是对的字段**——不是"后端今天就是这样"。

| 图 | 锁住的判据 |
|---|---|
| `s14b-ops-liveness-1440.png` | 三态分列：`存活` / `心跳卡死`（有 `lastHeartbeatAt` 但 1863s）/ `从未启动`（`lastHeartbeatAt=null` 且最近心跳列写"从未上报"）。合并这三态就是 R7.7 立这个接口的原因 |
| `s14b-discovery-1440.png` | 告警条在四屏之上（卡面目标句："在 /admin 顶部加告警状态条"）；三布尔不合并；启停编辑器勾的是草稿、丸是服务端事实；`defaultChannel` 与 `selectionReason` 同屏 |
| `s14b-banner-notready-1440.png` | `/ready` 回 **503 + `code=0`** 时告警条仍拿到明细：`依赖未就绪：Redis（unreachable）`。这条是 `getReadyProbe()` 注释里那句"request() 只在 code!==0 抛错"的**实测**，不是推断 |
| `s14b-engine-keys-375.png` | 375px 实测：`main` 右缘 = 375（不溢出），表容器 `scrollWidth 720 > clientWidth 341`（横向滚动而非挤压） |

375px 那张还抓到一处真缺陷：**徽标内的文本会被拆行**（"有登/记/行"三行）。
一个需要一眼读完的徽标换行就不是事实而是一个谜，故 `StatusPill` 加 `whitespace-nowrap`
（挤不下由 `.card.overflow-x-auto` 横向滚动承担）。这条是**看图看出来的**，
数值断言（`scrollWidth > clientWidth`）在修复前后都成立——所以它同时也是"只跑断言不取视觉"会漏掉什么的一个样本。

## 5. 三条不成立/做不到的，如实留着

1. **四屏主路径在 CI 的阻塞档结构上不可达**，原因不是用例没写：mock 会话的
   `is_admin` 恒为 `false`（`lib/api/auth.ts` 的 `MOCK_ME`），而 `/api/v1/admin/*` 与
   `/api/v1/system/ready` 都在演示态豁免清单里（STEP-15b 的口径：后台跨用户读面与部署事实不造样例）。
   ⇒ 阻塞档能测的是权限分层与版式（①～④条），四屏本体由 §3 的 7 条渲染契约 + §4 的视觉取证覆盖。
   要让它可达，改的是 mock 会话身份（一行 `is_admin: true`），那是别人的注册契约，交规划方裁定 ⇒ **P-88**。
2. **F-15 的第六组 `auth/backchannel-logout` 前端消费数恒为 0，而且应该恒为 0**：它是
   IdP→后端的服务器到服务器端点（STEP-19 的 S19.1.4 已按"只带 cookie 的登出回调 → 200 且会话失效"判过）。
   卡面"六组端点前端消费数均 ≥1"这句对它不成立 ⇒ 同记 **P-88**。
3. **`/admin/categories`、`/admin/discovery/config` 的读侧、`/admin/article-fallback` 三个端点在前端 0 消费**
   （STEP-28 / S10.V15.2 交付的是后端面）。它们不在本卡点名的四屏里，本卡不顺手扩屏——
   第五张屏该由 owning 卡画，否则又是一次越界。

## 6. 反证与一条自曝

两条判据都跑了变异，确认不是恒绿：

| 判据 | 变异 | 结果 |
|---|---|---|
| "取消当前默认渠道后保存，发出的 `default` 必须跟着换" | `DiscoveryChannelsPanel.tsx` 的跟随分支加 `&& false` | ❌ 红：`expected to be called with [ [ 'b' ], 'b' ]`（实发 `["b"], "a"`） |
| "探针读不到 ⇒ 画未知，不画健康" | `AlertBanner.tsx` 的 `unreadable` 分支 `tone: "unknown"` → `"ok"` | ❌ 红：`expected null to be truthy` |

**自曝**：第一条判据的**上一版是假绿的**。它判的是 `select.value === "b"`，
而 happy-dom 里 `select` 的 DOM value 会被 `options`（只列启用中的渠道）自动纠正——
组件 state 里那个悬空默认照样发得出去，判据看不见。改成判**发出的载荷**之后，
同一个变异才红。这条写在这里是因为它属于本仓最贵的那族失败：**断言读的是渲染残影，不是发出去的东西**。

## 7. 采集配置屏（V0.17 增量句点名的另一半，随后一批）

增量表那句是"余 3 项（告警条、**采集配置页**等）沿用现有组件与 `LoadingErrorShell`，不新造设计体系"。
告警条在 §1–§6，这一节是采集配置页。它补的是本卡此前 0 消费的两组端点：
`GET/PUT /admin/categories` 与 `GET/PUT /admin/article-fallback`（改前实测：`grep -rn` 在前端 0 命中）。

落成：`components/admin/CollectionConfigPanel.tsx`（第 5 个 tab `?screen=collection`）+
`lib/api/admin-ops.ts` 四个 typed 函数（`getCategories` / `putCategories` /
`getArticleFallback` / `putArticleFallback`）。没有新造组件：两张卡都走 `LoadingErrorShell`
与 `StatusPill`。

屏上三处"不能画错"的地方，都不是这里的偏好而是后端已经写死的约束：

1. **分类清单必须留着「其他」**——缺它后端直接 10005，所以那一行的停用与移除都是禁用的，
   并挂一枚"兜底分类"丸说明为什么不能动（普通分类两项可操作，否则这条判据是在测"整个界面都禁用"）。
2. **顺序是数据不是视图**——声明序即自动分类的优先级与筛选项顺序，所以"上移/下移"必须改变
   **发出去的载荷**。判据就按载荷写（`putCategories` 收到 `["其他","科技"]`），
   这是 §6 那条自曝的直接产物：只看 DOM 会看见渲染残影。
3. **`providers: null` 与显式名单是两种状态**，而 `PUT` 只能表达后者——
   `null` = 凡凭据就绪的都可用（新配好 Key 的自动进名单），`[]` = **一家都不打**（开着但永不生效）。
   所以：读侧把"不限制"显式画出来；写侧在 `enabled` 且（缺日预算 或 名单为空）时
   **禁用保存并给出那两句原因**（D-V12-20 拒绝"可无上限开启付费调用"）。
   勾任一供应商前，界面上先写明"这一步把不限制改成显式名单，此后新供应商不会自动进来"。

写权限不对称也照后端画：分类 operator 可写，付费兜底**只有 admin 可写**（读侧都是 operator），
所以 operator 看到的是"本屏对 operator 只读 + 该找谁"，而不是一个点了会拿 10004 的按钮。

读数增量：`test:unit` 49 files / **415 tests**（本批 +5 条渲染契约，含两条角色/锁定判据）、
`tsc --noEmit` 0 错、`next lint` rc=0、mock 与 `MOCK=false` 两档构建 rc=0
（`/admin/ops` 由 8.18 kB 涨到 **10.5 kB / first-load 129 kB**，涨的是这一屏）、
mock 产物 e2e **31 passed / 11 skipped / 0 failed**。反证一条：把保存按钮的
`disabled={fbSaving || fbBlocker !== ""}` 改成 `disabled={fbSaving}` ⇒ 那条"两条硬约束"判据红，
确认拦的是**能不能提交**而不是"有没有一句话"。

**卡面已经落后于自己的增量**：字段 5 写"交付四屏"、字段 8 里没有采集配置页这条三级任务，
而增量表要求做它——现在实际是 5 个 tab。登记 **P-91**（与 P-86 同族：卡面文字需按现读更正，
执行方不改卡面）。

## 8. 三绿

验收提交待回填。本卡零 `apps/api/**` 改动 ⇒ 零 pytest 新增，`SKIP_BASELINE_WIN` 保持 **653**。
