# STEP-17 需求基线补全与门面文档纠偏

| 字段 | 值 |
|---|---|
| 归属-切片 | S-M4 未纳管域补齐 |
| 归属-需求 | **全部 12 条**（REQ-F-001…008 / NF-001…002 / C-001…002）；冲突 C-3/C-4/C-5 |
| 归属-方案 | 04 §4.13、`coverage §1/§5` |
| 里程碑 | M4 |
| 档位 | haiku + 👤 人　理由：填模板、拆目录、改注释属低不可逆性；但「需求实现度」结论需人签字。**升级条件**：若发现某条需求「文档声称已实现而代码无锚」涉及对外承诺 ⇒ opus |
| 规模 | 中（≈1 人日） |
| 依赖 | Depends on：无（零依赖，可与 M0 并行的纯文档卡）。Blocks：STEP-12 |
| 基线 | main@13acacc |
| 剩余原子任务 | 7（👤 1） |

## 目标
`docs/02_requirements/` 从「单文件 12 条、无状态字段、子目录全空」变成可机检的需求基线，且门面文档（AGENTS/roadmap/代码注释）不再含有被本轮实测否证的陈述。

## 输入（实测）
- `features/`、`non-functional/`、`constraints/` 三目录**只有 `.gitkeep`**；`inbox/` 只有 README 模板（`coverage §1`）⇒ 按目录检索需求必然落空，这是 V0.6.0 只覆盖 2/12 的结构性原因之一（02 §5.2）
- 12 条需求全在 `product-requirements.md`，分节行号 `:55/:79/:86/:93/:100/:106/:113/:121/:132/:138/:149/:160`；**除 F-001 外均无状态字段**
- `AGENTS.md:75`「站内通知全链路已通」vs `:77`「写侧/读侧 history 待建 R1.2b/c/d」；代码实况：读侧已在（`system.py:323/:367`）
- `roadmap.md:95` 仍 `[ ] 治理脚本入 CI 强制步`，而 `ci.yml:97-105` 已阻断（`gen_contracts --check` + `check_docs_consistency`）
- `app/api/v1/admin.py:522` 过期注释「投递未实接」，而 `services/push.py:59-62` 已实接
- REQ-NF-002「CORS 白名单」：全仓无 `CORSMiddleware`/`allow_origins`；`core/security.py:440`「**不含 CORS**——前端经 `next.config.mjs` rewrites 同源代理」
- ⚠ `scripts/check_docs_consistency.py` 已在 CI 校验「backlog 引用路径存在」+「行号 ≤ 文件实际行数」⇒ 本卡写错行号会直接把 CI 弄红

## 输出（文件）
`docs/02_requirements/features/*.md`、`non-functional/*.md`、`constraints/*.md`、`product-requirements.md`（加三向表 + 指向子文件）、`AGENTS.md`、`docs/04_engineering/roadmap.md`、`apps/api/app/api/v1/admin.py`（仅删过期注释）、EVD-V3-17

## Execution Steps
1. [ ] 📄 **S17.1.1** 12 条需求按目录拆分（`features/REQ-F-00x-*.md` 等），每条头部三字段：`实现度`（已实现/部分/骨架/未实现）、`验收锚`（具体测试文件或「无」）、`最后核验 commit`
   - S17.1.1.1 实现度取值必须来自本规划 01/coverage 的实测条目，不得凭印象
   - S17.1.1.2 拆分后 `product-requirements.md` 保留摘要 + 链接（避免双源；若双源则 `check_docs_consistency` 红）
2. [ ] 📄 **S17.1.2** REQ-NF-002 的 CORS 条目改写为「经 `next.config.mjs` 同源 rewrites 达成，无 CORS 中间件」并引 `security.py:440`；**不排 CORS 开发任务**（C-3）
3. [ ] 📄 **S17.1.3** `product-requirements.md` 增「需求 ↔ STEP ↔ 测试锚」三向表，内容与 04 §4.3 同源（一处改两处，需一致性核对）
4. [ ] 📄 **S17.2.1** `AGENTS.md:75/:77` 矛盾更正为单一陈述（读侧已在；待建项改为「事件/手动路径落库」这一真实缺口，见 19 S19.1.1）
5. [ ] 📄 **S17.2.2** `roadmap.md:95` 勾掉，证据指向 `ci.yml:97-105`；**禁止重复排期**（C-5）
6. [ ] 🛠📄 **S17.2.3** 删 `admin.py:522` 过期注释（只删注释文本，不改代码行为）
7. [ ] ✅ **S17.2.4** 跑 `python scripts/check_docs_consistency.py` ⇒ rc=0，读数入 EVD

## 验收标准
- [ ] 三个需求子目录不再只有 `.gitkeep`；12 条各有一文件且三字段齐
- [ ] 每条需求能回答「有没有测试锚」；回答「无」的必须同步在 backlog 立项（不允许静默留空）
- [ ] `grep -n '待建 R1.2' AGENTS.md` 无残留（判据先过可满足性检查）
- [ ] `roadmap.md:95` 已勾且引用行号真实存在
- [ ] `check_docs_consistency.py` rc=0；`git diff --stat` 显示本卡**未改任何行为代码**（仅注释行）

## 验证命令
```bash
find docs/02_requirements -name '*.md' | sort                      # 期望 ≥12（拆分后）
ls docs/02_requirements/features/ | grep -c 'REQ-F'                 # 期望 8
python scripts/check_docs_consistency.py; echo rc=$?
grep -rn 'CORSMiddleware\|allow_origins' apps/api/app | wc -l       # 期望 0（文档新表述与之一致）
git diff --numstat HEAD -- apps/api/app | awk '$1+$2>0{print}'      # 只应命中 admin.py 注释行
```

## 证据路径
`docs/06_validation/evidence/EVD-V3-17/`

## 允许修改
`docs/02_requirements/**`、`docs/00_governance/project-map.md`、`docs/04_engineering/{roadmap,backlog}.md`、`AGENTS.md`（仅矛盾两处 + 状态行）、`apps/api/app/api/v1/admin.py`（仅注释）
## 禁止修改
任何代码行为、`packages/contracts/**`、`alembic/**`、`.github/**`、`docs/任务规划V0.6.0/**`（历史版本不改写，勘误只进本版）

## 依赖与阻塞
- Depends on：无　Blocks：STEP-12
- 阻塞条件：① 拆分需求文件导致 `check_docs_consistency` 报路径失效 ⇒ 先修引用再继续；② 某条需求实现度无法由现有证据判定 ⇒ 标 `证据不足` 并入 05 §1 未决，**不得**填「已实现」
