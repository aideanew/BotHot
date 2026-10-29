# EVD-V22-62 STEP-62 需求判词纠真：读数与判据

卡：[docs/任务规划V0.22.0/steps/STEP-62-需求判词纠真.md](../../../任务规划V0.22.0/steps/STEP-62-需求判词纠真.md)
日期：2026-10-29｜允许面：`docs/02_requirements/**`、`.github/workflows/ci.yml`（仅 `continue-on-error` 那一行）、卡面、卡表、07、本目录｜**禁止面：一切代码与测试（本卡零代码改动）**

## 1 改了什么（逐条）

| # | 文件 | 字段 | 旧判词 | 新判词要点 | 依据 |
|---|---|---|---|---|---|
| 1 | `docs/02_requirements/product-requirements.md` 71 | REQ-F-005 实现度 | 「部分：组件层已证…真后端端到端仍未测」 | **已实现（命题范围：`/chat` 契约五态）** | STEP-60 交付；run `40808385199` 步 11 `5 passed (2.8s)` + 步 12 守卫 `ok=5 skipped=0 failed=0`（[EVD-V24-60/s60_readings.md §6.2](../EVD-V24-60/s60_readings.md)） |
| 2 | 同上 74 | REQ-F-008 实现度 | 「部分（后端读面齐…）」 | **已实现（命题范围：四屏）** | run `40808385199` 步 13 `6 passed / 1 skipped`（同上 §6.2） |
| 3 | 同上 85 | REQ-NF-002 实现度 | 「部分（…SQL 注入无机检用例）」 | **已实现（命题范围）** | SEC-006 于 STEP-49 收口（[EVD-V21-49](../EVD-V21-49/)） |
| 4 | 同上 93 | REQ-C-001 实现度 | 「部分（…一致性本身无机检）」 | **已实现** | STACK-001 于 STEP-50 收口（[EVD-V21-50](../EVD-V21-50/)） |
| 5 | 同上 94 | REQ-C-002 实现度 | 「部分：…端口表两行与实际不符待裁（P-78）」 | **已实现（按 D-V21-05「文档跟实况」口径）** | `docs/03_solution/decisions/decision-log.md:146` |
| 6 | 同上 110 / 113 / 115 / 116 | 三向表「测试锚」列 | F-005 写「`r19-chat-stream.spec.ts` **零执行**」；F-008 只列文件名无读数；NF-002 写「SQL 注入面与 SameSite：**无**」；C-001 写「**无** → backlog STACK-001」 | 四条均换成具名锚 + 读数（F-005 加 run 步号与守卫读数、F-008 加 `6 passed / 1 skipped`、NF-002 与 C-001 换成实体测试/门脚本） | 同上 1 / 2 / 3 / 4 |
| 7 | 同上 119 | 无锚需求数 | 2（REQ-C-001 整条 + NF-001 三条 SLA 子项） | **1**（只剩 NF-001 的三条 SLA 子项） | 同上 4 |
| 8 | `features/REQ-F-005-rag-chat.md` | 头部 `实现度` + 判据表两行 + 原「为什么不能升格」一节（改名「命题范围与未覆盖面」） | 「部分」 | 「已实现（命题范围：`/chat` 契约五态）」 | 同 1 |
| 9 | `features/REQ-F-008-admin-console.md` | 头部 `实现度` + 原「实现度写「部分」」一节（改名「命题范围与未覆盖面」） | 「部分」 | 「已实现（命题范围：四屏）」 | 同 2 |
| 10 | `non-functional/REQ-NF-002-security.md` | 头部 `实现度` + 表第 26/30 行 + 原「无锚项的处置」一节 | 「部分」 | 「已实现（命题范围：五项）」 | 同 3 |
| 11 | `constraints/REQ-C-001-tech-stack.md` | 头部 `实现度` + `验收锚: 无` → 列 `scripts/check_docs_consistency.py` + 原「无锚的替代机制」一节 | 「部分」/「验收锚: 无」 | 「已实现」/锚为常驻门脚本 | 同 4 |
| 12 | `constraints/REQ-C-002-port-allocation.md` | 头部 `实现度` + 原「为什么仍是「部分」」一节（改名） | 「部分」 | 「已实现（按 D-V21-05 口径）」 | 同 5 |

字节量：`git diff --numstat` 六个文件分别 `13/7`、`13/7`、`21/8`、`16/6`、`15/8`、`10/10`（增/删），
无整文件重写（行尾未翻动的证据就是这些小数；`git` 的 CRLF 警告是本机 checkout 的既有状态，不是本卡引入）。

## 2 判据逐条

### 2.1 ① 每条新判词带证据路径 —— 通过

12 条改动逐条对应上表「依据」列，全部是仓内可读路径或 run id：
`EVD-V24-60/s60_readings.md` §6.2（run `40808385199`）、`EVD-V21-49/`、`EVD-V21-50/`、
`docs/03_solution/decisions/decision-log.md:146`。没有一条只写「已修复」而不给出处。

### 2.2 ② `e2e-real` 最近 3 次 run 全绿 ⇒ 删 `continue-on-error`，否则保持并写明 run 号 —— **判为「保持」**

按 `e2e-real` 的**真执行**序列（skipped 不计执行读数，口径见 [s60_readings.md §6.3](../EVD-V24-60/s60_readings.md)）：

| 次序 | head | 结论 | run |
|---|---|---|---|
| … | `8b695ce` | ✓ | — |
| … | `de65373` | ✓ | — |
| … | `1eaf2d5` | ✓ | — |
| … | `ca9ba70` | **✗**（① loading 严格模式两命中，用例自身问题） | `40806609514` |
| … | `d6d67fc` | ✓（五条 `✓` + 守卫步真执行） | `40808385199` |
| 最近一次 | `f536398` | ✓（`CI` 六 job 全 success，`e2e-real` 22 步 `bad=-`） | `40810903457` |

按「末三次」两种口径算，结论相同：

- **按真执行序列**（本表）：`ca9ba70` ✗ / `d6d67fc` ✓ / `f536398` ✓ ⇒ 中间那次是红。
- **按本卡交付前的读数**（§6.3 写作时点）：`1eaf2d5` ✓ / `ca9ba70` ✗ / `d6d67fc` ✓ ⇒ 同样非三连绿。

⇒ **「连续三次绿」不成立** ⇒ 按判据字面保留 `continue-on-error`，并把 run 号写进卡面
（`40806609514` 那次红，`40808385199` / `40810903457` 两次绿）。

**排除 skipped 的口径**：`408aae2`、`9b0a037` 两次 `e2e-real` 是 skipped（上游 `backend` 红），
既非绿也无执行读数。把它们算成「不绿」只会让摘除条件更严，不会放宽，所以这个口径对「该不该摘」是安全的。

因此 **`.github/workflows/ci.yml` 本卡一个字节未动**：`git diff --name-only` 与 `git status` 均不含该文件
（见 §3）。这不是「漏改」，是判据 ② 的另一支结论。

### 2.3 ③ 文档一致性门 rc 0 —— 通过

```
$ PYTHONIOENCODING=utf-8 python scripts/check_docs_consistency.py
[info] 解析 D:\Code\AideanBotHot\docs\04_engineering\backlog.md
[info] 找到 23 个路径引用

检查完成：共 23 个路径引用，0 个不存在
[anchor] 语料 15 份，根路径文件锚 138 处（按 HEAD 判存在）
[ok] [anchor] 需求侧锚对账通过
[stack] 语料 15 份，含键值引用的行 7 行
[ok] [stack] 技术栈引用与实值一致

[ok] 文档一致性检查通过
rc=0
```

这道门的三段正好覆盖本卡改动面：路径引用（23 个）、需求侧锚（138 处，新增的
`apps/api/tests/test_sec006_sql_param_surface.py` 与 `scripts/check_docs_consistency.py` 都在其中）、
技术栈键值引用（7 行，C-001 开头那几条 `"next": "^15.5.28"` 引用属此段）。

## 3 字节级复核（本卡改动的完整清单）

```
$ git status --porcelain
 M docs/02_requirements/constraints/REQ-C-001-tech-stack.md
 M docs/02_requirements/constraints/REQ-C-002-port-allocation.md
 M docs/02_requirements/features/REQ-F-005-rag-chat.md
 M docs/02_requirements/features/REQ-F-008-admin-console.md
 M docs/02_requirements/non-functional/REQ-NF-002-security.md
 M docs/02_requirements/product-requirements.md
 M docs/任务规划-索引.md
 M docs/任务规划V0.12.0/00-README.md
 M docs/任务规划V0.22.0/04-剩余可执行大纲体系.md
 M docs/任务规划V0.22.0/steps/STEP-62-需求判词纠真.md
 M docs/任务规划V0.25.0/04-剩余可执行大纲体系.md
 M docs/任务规划V0.25.0/07-执行过程记录.md
?? docs/06_validation/evidence/EVD-V22-62/
```

12 个改动文件 + 1 个未跟踪目录 —— **零代码、零测试、零 `ci.yml`**。
这与卡面第 7 条「禁止修改：一切代码与测试」一致，可比对方式：`git show --stat <本卡提交>`。

其中三个路径不在卡面第 6 条「允许修改」的列举里，授权来源写在这里备查：
`docs/任务规划-索引.md`（§1/§5 回填）来自 V0.25.0 派工单 `06-下一批下发指令.md` §3 对 STEP-62 的明文要求
（「`docs/任务规划-索引.md` §5 的 16 行状态回填」）与索引 §7 维护纪律第 1 条；
`docs/任务规划V0.12.0/00-README.md` 是该版台账（P 表）的既有住处，每卡追加一行是本仓惯例；
V0.22.0 / V0.25.0 的两份 `04` 就是卡面说的「卡表」。

## 4 局限

1. **判词升格的面是「命题范围」，不是整条需求。** F-005 未覆盖 `FIRST_TOKEN_SLOW_MS` 慢提示与真网络错误 UX；
   F-008 未覆盖写路径（CRUD）——二者都写进了各自子文件的新节与 `product-requirements.md` 的括号里，
   读判词时必须连括号一起读。
2. **F-008 与 D-V21-06 的关系是本卡的判断点。** 那条裁决写「不为 mock 档造 admin 会话；后台四屏判词维持部分」。
   本卡只推翻后半句，理由是它的前提（除 mock 档没有别的档能跑到四屏）已被真后端档读数推翻；
   前半句至今照办（mock 档仍不造 admin 会话）。若规划方认为后半句应作为独立约束保留，
   这是本卡唯一需要回滚的一处，回滚方式是把 `REQ-F-008` 的两处改回「部分」并保留其余 11 条。
3. **本卡不重跑任何测试。** 五条判词引用的都是已归档读数；本卡只跑文档门（D-V22-01 第 1 条：单卡只跑它改到的测试，
   本卡没改测试）。
