# EVD-V3-17：STEP-17 需求基线补全与门面文档纠偏（V0.17.0 队列⑮）

- 日期：2026-10-23（Asia/Shanghai）
- 基线：`main@bf141d5`（依赖安全补丁批；开工时工作树干净，仅另一会话的 `.workbuddy-ai/` 未跟踪目录，未触碰）
- 卡面：`docs/任务规划V0.7.0/steps/STEP-17-需求基线补全与门面文档纠偏.md`
  （零依赖纯文档卡；Blocks：STEP-12）
- 环境：Win10 + Git Bash；本轮**不需要** PG/Redis/LangBot（纯文档 + 一处注释删除）；
  门禁用到的解释器：系统 `python`（stdlib 脚本）与 `apps/api/.venv`（ruff/mypy）。
- 本卡性质：只动文档与注释。`git diff --numstat` 里 `apps/api/app/**` 只命中
  `api/v1/admin.py`，且是 docstring 文本（见 §2.4）。

## 0. 现读（写之前先把卡面的输入核一遍）

| 卡面输入 | 现读结果 |
|---|---|
| `features/`、`non-functional/`、`constraints/` 只有 `.gitkeep` | 成立：三目录各仅 `.gitkeep`；`inbox/` 仅 README |
| 12 条需求全在 `product-requirements.md`，分节行号 `:55/:79/…/:160` | 12 条与编号成立（F-001…008 / NF-001…002 / C-001…002）；**行号只在 13acacc 时点成立**，本轮拆分前实际是 `:55/:79/:86/:102/:109/:115/:122/:130/:141/:147/:158/:169`（母文件被后续卡增补过） |
| 除 F-001 外均无状态字段 | 成立，但要更正一处：F-003 有一份**实现度小节**（`:93-100`，STEP-13 加的），卡面说"均无"过严 |
| `AGENTS.md:75` vs `:77` 矛盾 | 成立（第 75 行「站内通知全链路已通」、第 77 行「写侧/读侧 history 待建 R1.2b/c/d」） |
| `roadmap.md:95` 仍 `[ ] 治理脚本入 CI 强制步` | **不成立**：现读该行已是 `[x]`，并注明「2026-10-17 现读更正为已完成」⇒ S17.2.2 的前提过期，见 §2.3 |
| `admin.py:522` 过期注释「投递未实接」 | 行号漂了：该串现在 `admin_push` docstring（`:769`），另外**模块 docstring `:18` 还有一份同族过期口径**（"两个通道都不实接 + 未就绪转 50002"），卡面只点了后者中的一处 |
| `security.py:440`（CORS 说明） | 行号漂了：该 docstring 在 `:446-450`，`:440` 现在是 `code=PAYLOAD_TOO_LARGE_CODE` |
| 全仓无 `CORSMiddleware`/`allow_origins` | 成立：`apps/api/app` 命中 0 |
| ⚠ `check_docs_consistency` 会让错行号把 CI 弄红 | 成立，但范围比卡面写的窄：它**只扫 `docs/04_engineering/backlog.md` 里 `### … ✅` 小节内**的 `` `path:line` `` 引用（源码 `PATH_PATTERN` 限 `.py/.ts/.tsx/.mjs`）⇒ 本卡新增文档里的行号不会被它判，但仍会误导人，所以另跑一遍自研扫描（§3） |

## 1. S17.1.1 拆分结果（12 份 + 母文件降级为摘要）

```
docs/02_requirements/features/       REQ-F-001-multi-channel-push.md
                                     REQ-F-002-hot-cluster-daily-report.md
                                     REQ-F-003-knowledge-base-engines.md
                                     REQ-F-004-article-ingest.md
                                     REQ-F-005-rag-chat.md
                                     REQ-F-006-subscription-sync.md
                                     REQ-F-007-sso.md
                                     REQ-F-008-admin-console.md
docs/02_requirements/non-functional/ REQ-NF-001-performance.md
                                     REQ-NF-002-security.md
docs/02_requirements/constraints/    REQ-C-001-tech-stack.md
                                     REQ-C-002-port-allocation.md
```

每份头部三字段齐（`实现度` / `验收锚` / `最后核验 commit`）。母文件 `version` 1.0 → 2.0，
`updated` = 2026-10-23，§二/三/四 改为"摘要 + 链接"，删去与子文件重复的详文（含 F-001
那段 2026-10-12 的「本需求未闭环」——已被 STEP-23/STEP-26 否证，历史原文留在 git 里）。

### 实现度取值一览（逐条给"判词从哪来"，不给印象）

| 需求 | 实现度 | 取值来源 |
|---|---|---|
| F-001 | 已实现 | `EVD-V3-19/verdicts.md` 判「已确认」+「需要谁接着做：无」；外部前置（微信 ClawBot 需部署）单列 |
| F-002 | 已实现 | 同上判词；`AGENTS.md` 热点段「评分已接线」；HOT-005 是显式排除项 |
| F-003 | **部分** | coverage 原句「已诚实标注但未实现…唯一成片的骨架区」+ `EVD-V17-30/s30_3_step13_verdict.md`（`NotImplementedError` 计数 16，只降不升）+ D-V3-03 |
| F-004 | **证据不足** | 卡面 S17.1.1.1 禁止凭印象：coverage/V0.6.0/V0.7.0 的任何 01 基线**都没有** F-004 的实现度判词（只有"✅ 有 STEP 覆盖"这一格，那是规划覆盖度）⇒ 按阻塞条件 ② 标证据不足并进 05 §2 未决 U-14 |
| F-005 | 部分 | `verdicts.md` 原判词「部分确认（后端在案/前端证据不足）」+ 前端流式 spec「未执行过」 |
| F-006 | 已实现 | 母卡面那句"X-8 STEP-04 行为层未做"已过期（S4.5.1 复跑读数 + STEP-06 E2E）；按现读写，历史文件不改 |
| F-007 | 已实现（命题范围） | `verdicts.md` 原判词带这个限定；主平台白名单配合另列 |
| F-008 | 部分 | coverage 的「前端 0 命中」已失效（STEP-14b 起有 `admin-ops-panels.spec.tsx`/`e2e/admin.spec.ts`），但 mock 档四屏结构上不可达（P-88）⇒ 既不写"已实现"也不沿用旧判 |
| NF-001 | 部分 | 四条里只有「单篇入库」有服务层读数（STEP-11），且该文件自己写明不得据此主张达标 |
| NF-002 | 部分 | 加密/生产守卫/密钥门有锚；SQL 注入与 SameSite 无断言 ⇒ 立项 |
| C-001 | 部分 | 实值与门面**今天**一致，但一致性无机检 ⇒ 立项 STACK-001 |
| C-002 | 部分 | `test_r19_ports.py` 七条双向；端口表两行与实际不符（P-78 未裁） |

## 2. S17.2 四处门面纠偏

### 2.1 `AGENTS.md`（三处，卡面允许「矛盾两处 + 状态行」）
1. **矛盾合并**：原第 75 行「站内通知全链路已通——Redis pub/sub 投递侧 + SSE 订阅侧…」与
   第 77 行「写侧/读侧 history 待建 R1.2b/c/d」→ 合并为一条四腿陈述（存储层 / 写侧三路径 /
   读侧 history+read / SSE+前端 Bell），并写明旧第 77 行是被实测否证的陈述。
   判据 `grep -rn '待建 R1.2' AGENTS.md` 现读**无残留**（卡面验收第 3 条）。
   ⚠ 这里有一条必须写下来的判断：该判据是**字符串形**的，而"合并后的正确陈述"天然要提到
   被更正的那句旧话——第一版我照抄了旧串（`待建 R1.2b/c/d`），于是"更正到位"与"grep 为空"
   互斥。处置是**改述而不删证**（新句：「旧第 77 行把写侧与读侧 history 写成待建
   （R1.2 的 b/c/d 三项）」），既满足字面判据也保留可核对的指向。
   这不是把判据改松：卡面自己就要求「判据先过可满足性检查」，这条正是它要抓的形态。
2. **版本行**：`"next": "^15.5.24"` → `^15.5.28`，并把 `product-requirements.md:134` 这个
   已失效的行号锚改成符号名（母文件刚被重构，行号锚必然漂）。
3. **状态行**：领先 tag 的提交数 15 → **286**（`git rev-list --count v1.0.0..HEAD` 现读）；
   测试读数 1002/4 → **2258 / 6 / 4 deselected**（`@ci` run 39885880010 @3491054 原文），
   并记下 `@win` skip 基线 666 与"本机 10-23 无 PG ⇒ 连库以 @ci 为准"。

### 2.2 `REQ-NF-002` 的 CORS 条目（S17.1.2 / C-3）
需求文本改为「经 `next.config.mjs` 同源 rewrites 达成，无 CORS 中间件」，引
`apps/api/app/core/security.py` 的 `SecurityHeadersMiddleware` docstring（现读 `:446-450`），
并**不排 CORS 开发任务**（C-3）。同文件新增：`SameSite=Lax` 有设定无断言 ⇒ SEC-006。

### 2.3 `roadmap.md` 的「治理脚本入 CI 强制步」（S17.2.2）
现读：该行**早在本卡之前就已经是 `[x]`**（2026-10-17 有人按现读更正过），引用行号
`ci.yml:136-137`（`gen_contracts --check`）与 `:143-144`（`check_docs_consistency`）也真实存在。
⇒ 本卡对 roadmap **零 diff**，判据「已勾且引用行号真实存在」以现读满足；
卡面那句"仍 `[ ]`"是 13acacc 的过期读数（与 P-91/P-94 同一族：上一轮的"因为 X 所以不能做"前提会过期）。

### 2.4 `admin.py` 的两处过期注释（S17.2.3）
- 模块 docstring `:18`「两个通道都落接口与注册表，但都不实接…未就绪即转 50002」
  → 改为"历史口径更正"段：投递已实接（`services/push.py` 构造真 Provider），
  失败回执是 200 + `delivered=False` + reason（R7.5.4），不抛 503/不转 50002。
- `admin_push` docstring `:769`「本批诚实占位：校验全落地、投递未实接」→ 同口径更正。
- 行为零改动：`git diff --numstat -- apps/api/app` = `4 2 apps/api/app/api/v1/admin.py`，
  全部在 docstring 内；`services/push.py` 现读 `:61` `make_push_provider(channel)`、
  `:71` `await provider.push(push_msg)`，模块 docstring 写「6 渠道均可实际投递」。

### 2.5 `docs/00_governance/project-map.md` 与 backlog
- 项目地图的 `02_requirements/` 表补三个子目录行（否则"按目录检索需求必然落空"这条
  结构性原因在入口图上仍然成立）。
- `backlog.md`：新增 **SEC-006**（SQL 注入面 + SameSite 无机检）与 **STACK-001**
  （门面版本声明与实值一致性无机检），均 ⬜；并更新 **TEST-001** 的缺口①——
  「无千篇量级性能用例」这半句由 STEP-11 闭合，但同时写明它们是 deselect 的手工读数，
  不是门禁。**无锚需求数 = 2**，全部有 backlog 项（卡面验收第 2 条）。

## 3. 门禁与自研扫描读数

- `python scripts/check_docs_consistency.py` → rc=0（`[ok] 文档一致性检查通过`）。
  它只覆盖 backlog 的 ✅ 小节，所以本卡另跑一份**新文档引用扫描**（`D:/tmp/check_req_cites2.py`）：
  抽出 12 份新文件里所有 `` `path[:line]` `` 形态引用（84 处），逐条解析并核对
  「路径存在」+「行号 ≤ 文件行数」；判完剩 **1 处 unresolved**，且那处是**故意**照抄卡面原文
  `security.py:440`（同一句里已给出全路径的现读修正），不是遗漏。
  扫描中真正常识性抓出的两个错并已改：① F-007 曾把 SameSite 写成"有断言"（实际无）；
  ② C-001 曾写 `providers/langbot*.py`（那是个包目录，不是文件）。
- `ruff check app tests` rc=0、`mypy app` 119 files 无问题（注释改动不影响）。
- 待跑：`evidence-check`（含敏感形门与 gitleaks）与三条 CI，见 §5。

## 4. 所有权与卡面判据

卡面允许：`docs/02_requirements/**`、`docs/00_governance/project-map.md`、
`docs/04_engineering/{roadmap,backlog}.md`、`AGENTS.md`（矛盾两处 + 状态行）、
`apps/api/app/api/v1/admin.py`（仅注释）。
本批 diff 全在这些面内，**两处超出**并声明：
1. `docs/任务规划V0.7.0/05-风险自检与局限.md` §2 未决表（U-08 闭合标注 + 新增 U-14/U-15）——
   依据是卡面阻塞条件 ②「标 `证据不足` 并入 05 §1 未决」。卡面写「§1」，而 §1 是风险清单、
   §2 才是未决表 ⇒ 按内容落进 §2（行号/节号漂移本身也是这类卡要抓的东西）。
2. `AGENTS.md` 第 3 处（测试状态行）超出"矛盾两处"字面，但属卡面明确允许的「状态行」。

## 5. CI 三绿（交付提交 `8de3a1a`，父提交 `bf141d5`）

三条检查 attempt 1 全部 success，且 CI 的五个 job 逐个绿：

| 检查 | run id | 结论 | job 明细 |
|---|---|---|---|
| CI（ubuntu） | 39888995918 | success | `workflow-lint` / `frontend` / `compose` / `backend` / `compose-smoke` 五个 job 全 success |
| CI-Windows | 39888995944 | success | `windows-dev` success（skip 门禁 `failed=0 total_skipped=666 baseline=666`，未知族 0） |
| Security | 39888995921 | success | 四扫描器无 BLOCK（`next` 升 15.5.28 后 pnpm-audit 与 trivy 清空） |

原始面按 D-V6-02 存证在本目录的 `ci_rest_runs_8de3a1a.json`（REST `runs/{id}` + `/jobs` 的
身份与结论字段，含 `head_sha`），不是"只抄 run 号"。

本卡是纯文档 + 一处 docstring：CI 的 `backend` job 绿同时说明
`admin.py` 的注释改动没有碰行为（ruff/mypy 也在那一步里）；`frontend` job 绿说明
拆分子文件没有打断任何文档链接引用面。

卡面 §8 的「run id 入 EVD」到这一节才成立——交付提交时刻本节只有一句"待回填"的声明，
这一点在 STEP-06 被独立验证者点过名，本卡同样如实标注而非事后抹平。
