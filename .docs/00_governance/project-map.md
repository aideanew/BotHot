# Project Map — AideanBot `.docs/` 文档体系地图

> 建立：2026-09-29（DOC-REORG W4.2.1）｜依据：《文档规范-v1.1.md》§10
> 维护规则：新增重要文档 → 同步 §3；目录结构变化 → 同步 §1/§5；本文件不存储任何需求/任务/决策正文。

---

## 1. 文档目录结构

```text
.docs/
├── 00_governance/          # 治理域
│   ├── 文档索引.md         #   唯一开发真源口径 + 总索引（含口径基线节）
│   ├── project-map.md      #   本文件
│   ├── 文档规范-v1.1.md    #   项目文档规范（管理者 2026-09-29 贴入落库）
│   ├── 开发流程.md         #   六步循环 + 仓库结构 + 门禁口径
│   ├── 编号互转表.md       #   T/R/D/N 编号体系互转（治理口径）
│   ├── 阻塞项登记表.md     #   D 系阻塞/风险/依赖登记
│   └── DOC-REORG-PLAN-SPEC-20260929.md  # 本次重组方案与取证记录
├── 02_requirements/        # 需求域
│   ├── 需求文档.md         #   当前需求基线 v0.3（产品目标+用户故事+验收标准）
│   ├── backlog.md          #   待办指针表（待批 SPEC/D 锁/N 缺口）
│   └── inbox/              #   新需求唯一入口（README 为入口规则）
├── 03_solution/            # 方案域
│   ├── decisions/          #   ADR-0001~0004
│   ├── solutions/          #   SPEC×5 + R8(RedFox) + R9(SSO logout)
│   ├── interfaces/         #   API接口文档 + 数据库文档 + 主平台统一账号接入说明/
│   └── test-plans/         #   SSO测试方案 + SSO联调测试方案
├── 04_planning/            # 计划域
│   ├── 当前态快照.md       #   当前态权威视图（每波次收尾强制刷新）
│   ├── 剩余任务原子化执行大纲-20260922.md  # T 系主大纲（§二 35WP + 竣工登记）
│   ├── R6-剩余任务原子化执行大纲-20260924.md  # R0~R6 编号唯一权威
│   └── R7-需求全景穿透与剩余任务方案大纲-20260924.md  # 16 问缺口矩阵
├── 05_execution/
│   └── 任务进度.md         #   台账总账（§一~§六十三，BOM 头，追加唯一锚）
├── 06_validation/
│   ├── reports/            #   M0实证/F项锚点/活体单篇/R6.1.1镜像取证/批量修复报告
│   └── evidence/t007/      #   R5.1 安全测试原始工件 ×7
├── 08_knowledge/
│   ├── RSS分析/            #   六模型 RSS 通道调研产出 ×6（rss 通道决策输入）
│   └── 交接提示词/         #   AI-CLI 助手(09-08) + 批量修复总管(09-19)
├── 09_archive/
│   ├── superseded/         #   被替代大纲/历史对账/讨论稿/裁定请求 ×14
│   └── inception/立项分析/ #   立项期原始材料 ×8（含 0 字节悬空件，审计保留）
└── 10_operations/
    └── 部署运维手册.md     #   compose 启停/回滚/巡检/隔离测试库
```

## 2. 文档关联关系

### 核心追溯链

```text
README/需求文档(产品目标) → 需求文档(U 故事) → SPEC/R8/R9(方案) → 大纲/R6/R7(波次计划)
    → 台账§(执行记账) → 当前态快照(收敛) + reports(验证) + evidence(证据)
新需求：inbox → backlog → SPEC → 大纲波次 → 台账
阻塞：D 锁 → 阻塞项登记表 → 解封后回写台账+快照
```

### 关键关联说明

| 来源 | 目标 | 关系 |
|---|---|---|
| 文档索引「口径基线」 | 全部数值引用 | 唯一当前基线，历史文档旧数不回写 |
| 需求文档 | SPEC/R8/R9 | 需求驱动方案 |
| ADR-0002/0004 | 接口/引擎实现 | 决策约束实现 |
| 大纲-20260922(T系) ↔ 编号互转表 ↔ R6(R系) | 台账 § | 编号权威链 |
| R7 16问矩阵 | R8/R9 立项 | 缺口驱动波次 |
| 台账 §n | 对应专项文档 | 执行记账→详情 |
| 06_validation/reports + evidence | 台账/索引引用 | 完成证明 |

## 3. 当前项目文档状态总览

| 文档 | 路径 | 状态 |
|---|---|---|
| 文档索引（口径基线） | 00_governance/文档索引.md | ✅ 活体 |
| 需求基线 v0.3 | 02_requirements/需求文档.md | ✅ 活体 |
| 当前态快照 | 04_planning/当前态快照.md | ✅ 活体（R7.7 批次） |
| 台账 | 05_execution/任务进度.md | ✅ 活体（§六十三） |
| API/数据库接口 | 03_solution/interfaces/ | ✅ 活体（前端契约权威） |
| ADR×4 | 03_solution/decisions/ | ✅ 活体 |
| SPEC×5、R8、R9 | 03_solution/solutions/ | 混合（M3 APPROVED；T4.3/T6.1 DRAFT 待批；R8 待批；R9 A侧交付 B侧待办） |
| project-map/backlog/inbox | 本文件等 | ✅ 2026-09-29 新建 |
| 归档 | 09_archive/ | 22 文件（14 superseded + 8 inception） |

## 4. 规范偏差登记（按复杂度裁剪 + 项目纪律）

1. `01_product/` 不建：产品目标单源 = 根 README + 需求文档 §一（复制即违反 SSOT）。
2. `07_release/` 暂不建：无对外发布事实；台账 + git 提交即变更记录。启用条件：首次正式对外交付。
3. `10_operations/` 为规范外扩展域（运维 runbook 体量足以独立成域）。
4. 存量文档**不回溯**改造为 REQ-F-/TASK- 编号；T/R/D/N 既有体系经编号互转表治理。新文档起走规范 ID（REQ-INBOX/REQ-F/…）。
5. `09_archive/superseded/` 兼收「并存历史快照」（如需求全景对账-20260924，台账 §42.11 记录并存非替代）。
6. dated 冻结文档（大纲/R6/R7/报告等）正文**只追加不回写**——项目「历史不回写」纪律，效力高于规范模板。
7. 台账兼任 Task-Index 与 Changelog 职能（追加唯一锚纪律），不另建 task-index/release-notes。
8. `r8-*` 文件名小写为历史偏差，保持不改名（引用稳定优先）。
9. 台账 >1MB 时再议内容级瘦身（本轮观察项）。

## 5. DOC-REORG 迁移对照（2026-09-29）

根级文件旧→新（高频引用者）：

| 旧（.docs/ 下） | 新 |
|---|---|
| 文档索引/开发流程/编号互转表/阻塞项登记表 .md | 00_governance/ |
| 需求文档.md | 02_requirements/ |
| API接口文档/数据库文档.md | 03_solution/interfaces/ |
| ADR/ | 03_solution/decisions/ |
| SPEC-*、R9-*、r8-* | 03_solution/solutions/ |
| SSO测试方案/SSO联调测试方案.md | 03_solution/test-plans/ |
| 主平台统一账号接入说明/ | 03_solution/interfaces/主平台统一账号接入说明/ |
| 当前态快照/大纲-20260922/R6/R7 | 04_planning/ |
| 任务进度.md | 05_execution/ |
| M0/F项/活体/R6.1.1/修复报告 | 06_validation/reports/ |
| t007/ | 06_validation/evidence/t007/ |
| RSS分析/、交接提示词_* | 08_knowledge/（后者入 交接提示词/） |
| 14 份历史讨论与被替代大纲 | 09_archive/superseded/ |
| 立项分析/ | 09_archive/inception/立项分析/ |
| 部署运维手册.md | 10_operations/ |

完整 71 行逐项映射与判据：`00_governance/DOC-REORG-PLAN-SPEC-20260929.md` §3/§10。
纪律：台账与冻结文档正文中旧路径保留原文，检索时按本表换算。

## 6. 非文档体系目录登记（不纳入 `.docs/` 治理）

| 目录 | 性质 | 备注 |
|---|---|---|
| `.workbuddy/`、`backend/.workbuddy/` | 执行体工具私有工作区（记忆/证据/tmp） | git 追踪；证据引用形如 `.workbuddy/evidence/*` |
| `.trae/documents|specs` | 历史工具产物 | 索引 §二 仍引用《AideanBot完整开发计划.md》 |
| `.project/` | 第三方参考项目集合 | LangBot/MediaCrawler/firecrawl 等 |
| `.docs/采集渠道/` | **他属会话 2026-09-29 在产（未跟踪）** | 归属待其收口后裁决（建议 08_knowledge 或 03_solution），本批不触碰 |
| `frontend/docs/` | 前端域文档 | 联调演练手册（契约基准指向 03_solution/interfaces/） |
