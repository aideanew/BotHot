# Backlog — 需求与工作待办指针表

> 建立：2026-09-29（DOC-REORG W4.2.1）｜依据：《文档规范-v1.1》§9
> **本表只承载指针与归类，不承载正文、不复述状态细节**——唯一事实源：《当前态快照》（收敛态）、《阻塞项登记表》（D 锁）、《任务进度》台账（执行记账）。

## 1. 待批方案（APPROVE 队列）

| 项 | 文档 | 头部状态口径 |
|---|---|---|
| SPEC-T4.3 飞书采集源扩槽 | `03_solution/solutions/SPEC-T4.3飞书知识库扩槽-20260922.md` | DRAFT 待批（注意：飞书=引擎位的立项语义已否决，改 `feishu_wiki` 采集源，见大纲 §十一） |
| SPEC-T6.1 微信通道与 Bot 接线 | `03_solution/solutions/SPEC-T6.1微信通道与Bot接线-20260922.md` | DRAFT 待批（前提已脱节，见 `04_planning/剩余任务原子化执行大纲-20260922.md` §十二） |
| r8 RedFox 对接余项 | `03_solution/solutions/r8-redfox对接活体实测与剩余任务方案大纲-20260928.md` | PLAN+SPEC 待 APPROVE（主体已实施；余项=其 §62.7 待用户决定） |
| R9 SSO back-channel logout B 侧 | `03_solution/solutions/R9-SSO-backchannel-logoutUri补齐-PLAN-SPEC-20260928.md` | A 侧已交付；B 侧 E1/E2/E3/E5 待管理者/运维 |

## 2. 开放阻塞锁（D 系指针）

> 全部状态以 `00_governance/阻塞项登记表.md` 对应小节为准；下表仅登记「存在哪把锁」。

| 锁 | 主题 |
|---|---|
| D3 | RedFox key/积分（测试 key 活体已通，生产 key 余额未验证） |
| D10 | 引擎凭据 coze/dify/fastgpt |
| D11 | 飞书采集源凭证 |
| D13 | 主平台 OIDC 白名单配置 |
| D15 | 镜像与运行态漂移（授权制） |
| D17 | scheduler/worker 容器缺失（R7.7 已修复，余项见登记表） |
| D18 | 第二发现渠道未实接（rss 占位在 registry） |
| D21 | RedFox searchUser 上游故障 |
| D22 | RedFox 优质库接口文档可信度降级 |
| D24 | CI frontend 无 PostgreSQL/无 e2e 门禁 |
| D25 | 调度器双重认领竞态（修复已落地，见登记表） |
| D26 | 仓库本地门禁反馈回路（preflight 已建，持续口径见登记表） |

已解封留痕：D14（RedFox key 验证 ✅）、D19/D23（测试隔离 ✅）、D20（镜像追平 ✅，见《文档索引》口径基线）。

## 3. 缺口登记（N 系指针）

N1~N13 原始登记：`09_archive/superseded/进度对账-18问-20260922.md` §9.4/§11（历史登记，只读）。
现行收敛状态一律以《当前态快照》为准（多数 N 项已吸收进 R0~R7 波次，见 `00_governance/编号互转表.md`）。

## 4. 新需求入口

任何新需求首先进入 `inbox/`（命名与流转规则见 `inbox/README.md`），不得直接开方案或改代码。
