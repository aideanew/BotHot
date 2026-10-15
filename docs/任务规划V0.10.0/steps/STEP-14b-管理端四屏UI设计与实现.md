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

## V0.9.0 → V0.10.0 本卡变更（基线 main@81cb997）

- **阻塞变更**：同 15，00E 前置解除；仍依赖 15 与 D-V3-06。
- 构建门：本卡验收命令的 `pnpm build` 必须带 `NEXT_PUBLIC_API_MOCK=false`（生产守卫，ci.yml:275）。
