# STEP-14b 管理端四屏UI设计与实现

> 基线 main@61358c3｜状态：⚪ 未开始

| 字段 | 内容 |
|---|---|
| 1 归属（执行者） | 规划方(Hark) |
| 2 验收者（与执行者分离） | 执行Agent，只输出 PASS/FAIL/UNKNOWN |
| 3 难度 / 里程碑 | 核心 / M2 |
| 4 来源 | F-15/F-16；ux_states.schema.json；V0.7.0 STEP-14 UI 部分 |
| 5 目标 | 为 0 消费的管理端点交付四屏：推送管理、运维存活、发现渠道、引擎密钥，并在 /admin 顶部加告警状态条。 |
| 6 输入 | apps/web/app/admin/page.tsx、AdminOpsSection.tsx、PushTasksTab.tsx 等既有组件 |
| 7 输出路径 | apps/web/app/admin/{push,ops,discovery,engines}/page.tsx；apps/web/components/admin/{AdminTable,StatusPill,AlertBanner}.tsx；apps/web/e2e/admin.spec.ts |
| 8 三级任务 | 见下 |
| 9 验收 | F-15 六组端点前端消费数均 ≥1；e2e 全绿；build 绿 |
| 10 命令 | `cd apps/web && pnpm build && pnpm test:e2e -- admin.spec.ts` |
| 11 证据 | docs/任务规划V0.8.0/evidence/61358c3-14b/ |
| 12 允许修改 | apps/web/app/admin/**、apps/web/components/admin/**、apps/web/e2e/admin.spec.ts |
| 13 禁止修改 | apps/web/lib/api/**（归 15）、apps/api/** |
| 14 依赖 / 阻塞 | 15 / D-V3-00、D-V3-06 BLOCKING |
| 15 档位 | T3 |
| 16 升级条件 / 规模 | 后端缺字段 ⇒ 回 14a，不在前端造数据 / ≈2.5 人日 |

## 三级任务

### S14b.1 设计
- **S14b.1.1** 信息架构：/admin 侧栏 5 入口（总览+四屏），路由与权限守卫复用 AuthGate
- **S14b.1.2** 每屏四态稿（加载/空/错误/成功）对齐 ux_states
- **S14b.1.3** 密钥类字段只显示掩码，复制/轮换走 ConfirmModal

### S14b.2 通用件
- **S14b.2.1** AdminTable：列配置、排序、分页（接 usePaged）、行操作
- **S14b.2.2** StatusPill：健康/降级/故障三色 + 文本，满足对比度
- **S14b.2.3** AlertBanner：读 /ready 告警字段

### S14b.3 四屏
- **S14b.3.1** 推送：任务列表、重试、失败原因
- **S14b.3.2** 运维存活：各 worker 心跳与延迟
- **S14b.3.3** 发现渠道：渠道列表、启停
- **S14b.3.4** 引擎密钥：列表、新增、轮换、停用（掩码）

### S14b.4 验收
- **S14b.4.1** e2e：四屏各一条主路径 + 一条错误态
- **S14b.4.2** 移动宽度 375px 不溢出；键盘可达
- **S14b.4.3** 执行 Agent 独立验收，输出 PASS/FAIL/UNKNOWN

## 执行记录（V0.11.0 第二增量 · 2026-10-15 · @win 实现并自验）

前置已就位：STEP-15 的 S15.2.3 先把消费面建好（`lib/api/admin-ops.ts` 七个 typed 函数 + 11 条
stub-fetch 单测），本卡才有东西可画。

| 三级任务 | 状态 | 事实 |
|---|---|---|
| S14b.1.1 侧栏 5 入口 IA | ⚠ **显式偏离** | 做成**一条路由 `/admin/ops` + 四屏 tab**，并用 `?screen=` 保持深链可分享；不是 /admin 侧栏新增 5 个入口。理由：运维读的是同一时刻的四张脸，分五个路由会让"切屏=换页=重取数"变成五种实现；深链需求由 query 满足。**这一条不能算完成 5 入口 IA**，要侧栏入口请另补一次改卡 |
| S14b.1.2 四态对齐 ux_states | ✅ | 每屏 loading/error(带重试)/empty/success 四态；empty 态**不是**"全绿"——`processes=[]` 与 `channels=[]` 都写成故障信号文案 |
| S14b.1.3 密钥掩码 + ConfirmModal | ✅（比卡面更严） | 后端从不回显明文，输入框 `type=password` 提交即清空、不进 URL；`keyId` 掩码成 `abcd…5678`，有单测锁完整句柄不出现在 DOM。撤销/停用走 `ConfirmModal`；**登记不走 ConfirmModal**——那个组件只支持选项不支持自由文本，硬塞会把明文放进"破坏性操作"文案的弹窗里 |
| S14b.2.1 AdminTable（列配置/排序/分页/usePaged/行操作） | ❌ **未做** | 四屏都是窄表（≤7 列、无排序、无分页），没有数据面需要 `usePaged`；为"通用件"提前抽象等于给假想需求做设计。要做的是先有第五张需要分页的屏，再回头抽 |
| S14b.2.2 StatusPill 三色 | ✅ | `components/admin/StatusPill.tsx`：ok/degraded/bad/**unknown** 四态 + 必带文本（红绿色觉缺陷下纯色丸不可分辨；对比度取深字浅底） |
| S14b.2.3 AlertBanner 读 /ready 告警字段 | ❌ **未做** | `/ready` 的 alerting 字段在信封 `data` 里、不在 `checks`（此前那处契约已入库），但本卡没有告警横幅——它属于 STEP-05「采集静默告警」的读侧，先把那组端点定下来再画，否则画的是猜出来的形状 |
| S14b.3.1 推送 | ✅（范围已收窄） | `PushConsolePanel`：通道下拉 + 触发 + **终态回执**。`delivered=false` 画"未投递 + 原因"并明写"这是 200 回执不是异常"。任务列表/重试沿用既有 `PushTasksTab` 与 admin jobs 面，未重画 |
| S14b.3.2 运维存活 | ✅ | `LivenessPanel`：按 EXPECTED_PROCESSES 全景渲染，"从未启动"与"心跳卡死"分列不同徽标（这是 R7.7 立这个接口的唯一理由，合并就白做了） |
| S14b.3.3 发现渠道 | ✅（启停为只读） | `DiscoveryChannelsPanel`：三布尔不合并 + `defaultChannel=null` 显示"不设默认，仅做清单 diff"。**没有做启停开关**：后端只有 GET，启停是 `discovery_channels` 配置项，放个开关等于假装存在 PATCH 端点 |
| S14b.3.4 引擎密钥 | ✅ | `EngineKeysPanel`：登记/轮换/停用 + `masterKeyConfigured=false` 时禁用按钮并说明"会以 50002 拒绝，不回落明文"；`decryptFailed` 单独标"解密失败" |
| S14b.4.1 e2e 四屏主路径 + 错误态 | ⚪ 未跑 | 本机无后端栈（PG/Redis 不可达，D-V4-01 下 e2e 归 @ci）。**单测已覆盖 6 条渲染契约**代替，e2e 待 STEP-00E/容器就绪 |
| S14b.4.2 375px 不溢出 / 键盘可达 | 🟡 部分 | 密钥表用 `overflow-x-auto` + `min-w-[720px]`（窄屏横向滚动而非挤压）；tab 是真 `<button>` 且有 `aria-current`，阈值选择器有 `aria-label`。**未做**真机 375px 截图核对 |
| S14b.4.3 独立验收 | ⚪ 待做 | 本卡是执行方自验（typecheck/lint/vitest/build 四绿 + 6 条渲染单测），**不满足"写的人不判自己过"**；需独立验证者只看 diff 与读数出 PASS/FAIL/UNKNOWN |

@win 读数（2026-10-15 15:3x）：`tsc --noEmit` 0 错；`pnpm run lint` → `No ESLint warnings or errors`；
`pnpm run test:unit` → **47 files / 383 tests 全过**（本卡新增 6 条渲染契约 + 15 的 11 条）；
`NEXT_PUBLIC_API_MOCK=false pnpm run build` → 编译成功，路由表出现 **`/admin/ops 6.88 kB / first-load 123 kB`**。

## V0.9.0 → V0.10.0 本卡变更（基线 main@81cb997）

- **阻塞变更**：同 15，00E 前置解除；仍依赖 15 与 D-V3-06。
- 构建门：本卡验收命令的 `pnpm build` 必须带 `NEXT_PUBLIC_API_MOCK=false`（生产守卫，`ci.yml` frontend job "Build" 步的 `env:`；原记 `ci.yml:275` 已因 2026-10-17 backend job 插入 "Migration roundtrip" 步而下移，故按步名定位）。

## 裁决已签（V0.11.0 第四节第 2 步 · 2026-10-15 12:04）
| 项 | 变化 |
|---|---|
| D-V3-06 | 补最小管理界面（密钥登记 / 渠道 / 探针 / 推送终态 / 告警）；权限沿用 admin，不新增 RBAC |
| D-V3-03 | 未实接的引擎在 UI 上必须显式标「未接入」，**不得抛 500**（`engines.py:121-122` 的 403/10004 口径不变，只是文案要可辨） |
| D-V3-00 | UI 由执行方亲自完成已获授权；**阻塞从「未授权」改为「依赖机可用」**：`pnpm install --frozen-lockfile` + `NEXT_PUBLIC_API_MOCK=false`，并按 STEP-00X 在 Win10 上可复现 |
| 验收面 | 本卡 Done 只能由 `@ci` **ubuntu-latest** 判定；`@win` 读数只算开发烟测，`@linux` 为依赖机本地验证 |
| 标签 | 依 D-V6-01，本卡 `@dep` 已全部改写为 `@linux`/`@ci` |
