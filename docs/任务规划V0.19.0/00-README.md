# 任务规划 V0.19.0（AideanBotHot · 基线 main@9c66add · 2026-10-23）

## 0. 一句话
V0.18.0 的发布段已走完：STEP-32、33 修好两个发布阻断，**v1.1.0 已打 tag**（指向 `49c3bed`），STEP-38 也已收口，主干三绿。
但规划方本轮深挖出一个比 v1.1.0 两个阻断更直接的泄漏：**每推送一次、每用 JustOneAPI 采集一次，渠道凭据就原样写进一次应用日志**（P-113）。
它是安全核心问题，规划方本轮已亲自修好（STEP-40，`log_redaction.py` + 审计路径参数遮蔽），下一步由执行助手发 **v1.1.1**（STEP-42），再继续 V0.18.0 留下的 34 → 35 → 36 → 37 → 18。

## 1. 规划快照
```yaml
snapshot:
  规划日期: 2026-10-23（Asia/Shanghai）
  仓库: https://github.com/aideanew/BotHot
  git_branch: main
  git_commit: 9c66add        # 本版基线；上一版 ecd78e2（V0.18.0 规划）/ f62054b（STEP-32 卡面增量），其间 11 个执行提交
  工作区: 干净（apps/api/.coverage 为测试产物，未跟踪）
  CI@9c66add: CI 39941688898 ✅ / CI-Windows 39941688925 ✅ / Security 39941688895 ✅
  tag: v1.1.0 → 49c3bed（注释 tag，Tagger CodingHeader）；GitHub「Release」页对象不存在（只有 tag）
  本机@9c66add（@linux，PG16@5547 隔离库，驱动 postgresql+psycopg）: 2305 passed / 5 skipped / 4 deselected / 0 failed，186.56s，覆盖率 88%
  Alembic: 单头 ab1006c2a
  测试命令: cd apps/api && python -m pytest -q --cov=app（需 AIDEANBOT_TEST_PG_DSN 与 DATABASE_URL 指向测试库）
  剩余: 执行助手 7 张卡 / 33 项 / ≈6.5 人日；规划方 1 张门控卡（STEP-41，等外部条件）
```

## 2. 目录（固定 8 文件 + 新卡，命名规则见 docs/任务规划-命名规则.md）
| 文件 | 内容 |
|---|---|
| `00-README.md` | 本文件 |
| `01-事实基线与进度.md` | 拉取、CI、本机读数、V0.18.0 队列逐卡收口核对 |
| `02-需求复核与辩证分析.md` | P-109～P-113 终判；未实现需求盘点（真源联调、生产核查等）；辩证 |
| `03-裁决与契约增量.md` | D-V19-01～09（同步 decision-log）；契约变化（无） |
| `04-剩余可执行大纲体系.md` | 卡表、DAG、所有权、档位、完成定义、**附录 A：执行助手提示词（自包含）** |
| `05-风险自检与局限.md` | 风险、待用户输入、自检、局限 |
| `06-入库与双端一致.md` | 落盘、门禁、推送后读数 |
| `07-执行过程记录.md` | 规划方前 4 行；执行助手逐行追加 |
| `steps/STEP-40-日志出口凭据遮蔽.md` | 规划方本轮已做（核心安全） |
| `steps/STEP-41-真源联调冒烟.md` | 规划方门控卡（等外部条件） |
| `steps/STEP-42-发布v1.1.1.md` | 执行助手队列第一 |
| `steps/STEP-继承卡增量-V0.19.md` | STEP-34/35/37 的加项（P-109/110/111） |

## 3. 第一刀与启动顺序
1. **STEP-40（规划方，已交付本地并随本版提交）**：日志唯一出口加遮蔽；审计路径参数只留 UUID 与短标识符。
2. **STEP-42 发布 v1.1.1**（执行助手；40 所在 head 三绿后）：补建 v1.1.0 与 v1.1.1 两个 GitHub Release 页。
3. 之后：STEP-34 → STEP-35 → STEP-36 → STEP-37 → STEP-18（V0.18.0 卡面 + 本版增量）。
4. STEP-41 真源联调：外部条件满足才启动（见 05 §2）。

## 4. 与旧版本的关系
- V0.13.0～V0.18.0 卡面仍权威；本版只写增量（D-V11-07）。STEP-34～37 的卡面仍在 `docs/任务规划V0.18.0/steps/`，加项见本版继承增量。
- 冻结契约仍只在 `docs/任务规划V0.12.0/contracts/`（本版零契约变化）。P 表仍在 `docs/任务规划V0.12.0/00-README.md`，本版追加 P-113。
- 证据目录口径：本版新卡证据落 `docs/06_validation/evidence/EVD-V19-<卡号>/`；继承卡沿用 `EVD-V18-<卡号>/`。
