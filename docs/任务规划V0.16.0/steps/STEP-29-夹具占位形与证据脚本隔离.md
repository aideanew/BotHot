# STEP-29 敏感形门召回补缺、夹具占位形与证据脚本隔离

- 里程碑：M0 ｜ owner：执行 Agent-Guard ｜ 档位：sonnet（S29.1/S29.2 改安全判据，独立复核用 opus，每项 1 张券）｜ 估算：6 项 × 0.2 = 1.2 人日
- 来源：STEP-27 独立复查（`evidence/28c0d2e/review27_summary.md`）、执行方待裁三条（`EVD-V15-27/s27_readings.md` §四/§六）、28c0d2e 全仓普查（`evidence/28c0d2e/secret_census.md`）
- 裁决：D-V16-01～05
- 依赖：27 ✅。**后继**：26、05、10、28（这些卡会碰被门挡住的夹具或 reranker 同族写法；单执行助手按队列串行）
- D-14：本卡 ≤2 轮，第 3 轮熔断（rounds-check 机器执行）

## 为什么排第一
1. 28c0d2e 新门下仍有 **11 个自有文件**有命中：`apps/api/app/providers/reranker.py` 1（误报，P-45）+ 10 个测试夹具（`test_provider_contract.py` 11、`test_auth.py` 6、`test_provider_defects_p15_p17.py` 4、`test_backchannel_logout.py` 3、`test_push_providers.py` 3、`test_session_store_redis.py` 2、三个 manifest 测试各 1、`test_w1_push_domain.py` 1）。后续卡一碰就被挡，门没有豁免通道。
2. 召回补缺（S29.1/S29.2）会**新增**命中，必须先放宽规则再改夹具，否则夹具要改两遍。

## 允许修改
`scripts/guards.py`（只限 `SECRET_ASSIGN` 与源码模式相关函数）、`apps/api/tests/test_secret_shape_gate.py`、`apps/api/tests/test_guard_rounds.py`（只限 S29.6 的 CI 断言）、S29.4 列出的 10 个测试文件（**只改夹具字面量**，不改断言语义）、`docs/06_validation/evidence/EVD-V2-00/prove_dsn_policy.py`、`docs/06_validation/evidence/EVD-V15-27/s27_3_counts.py`（只改计数口径）、`docs/06_validation/evidence/EVD-V16-29/**`（新）

## 禁止修改
`apps/api/app/**`（含 reranker.py）、`apps/web/**`、`.gitleaks.toml` 规则语义、`.gitleaksignore`、冻结契约 `docs/任务规划V0.12.0/contracts/**`、文档面（code=False）判定、十条具名规则

## L3 原子任务
| L3 | 内容 | 判据（先红后绿） | 证据 |
|---|---|---|---|
| S29.1 | （P-44）`SECRET_ASSIGN` 的"赋值号后第一段至少 4 个字符"下限只在**源码模式**放开，让短左值进入源码判定 | 先红：复查 A 项 6 类（短左值 + 或运算 / 空值合并 / 逻辑或 / 三元两个分支 / 字符串拼接 / 括号或运算，字面量 ≥8 字符）各 1 条，改前 0 命中；改后全报。纯表达式 10 条（复查 A 项"不报"清单）仍 0。文档面逐文件读数与 28c0d2e 字节一致 | `EVD-V16-29/s29_1.txt` |
| S29.2 | （P-41 + P-44 第二半）带类型注解的赋值（键名 冒号 类型 等号 引号字面量）、带引号键名、下标赋值、`Field(default=…)`/`Field(…)` 带类型注解、大写常量 `*_PASSWORD`/`*_API_KEY` 前缀族：逐类评估，**能低误报的才收**，收不了的写明原因留登记 | 每类先红后绿成对用例；全仓自有源码（不含 `.project/`）新增命中逐行列出且每条人工判定"真字面量"；**新增误报 0**，否则该类不收 | `EVD-V16-29/s29_2.md` |
| S29.3 | （P-45）`getattr(对象, "属性名", 默认)` 这类**第二个参数是属性名字符串**的写法不当兜底值；默认值位（第三参数起）照判 | 先红：reranker.py 第 145 行 1 命中；改后 0。反证：第三参数是 ≥8 字符非占位字面量 ⇒ 照报 | `EVD-V16-29/s29_3.txt` |
| S29.4 | （P-42）10 个测试文件的夹具字面量换成 `SECRET_FAKE` 认得的占位形（尖括号说明、`${X}`、连续 x 或星号、`REDACTED` 开头）或字符串拼接；断言语义不变 | 普查脚本在本卡终态：**自有源码面 0 个文件有命中**；这 10 个文件的用例数与通过数改前改后一致（逐文件 `pytest --co -q` 计数 + 运行） | `EVD-V16-29/s29_4.txt` |
| S29.5 | （P-43）`EVD-V2-00/prove_dsn_policy.py` 自己隔离环境：f/l/m/n 四条在子进程里用清掉两个 DSN 的环境跑；`ci.yml` 该步置空串**保留**（双保险） | 先红：带 DSN 环境跑该脚本 4 FAIL；改后同环境 ALL PASS；不带 DSN 仍 ALL PASS | `EVD-V16-29/s29_5.txt` |
| S29.6 | （P-46 + 复查 D 项瑕疵）① `s27_3_counts.py` 改为按（文件,行号,规则）逐行对照，输出"少报 N / 新增 M"；② `test_guard_rounds.py` 把"任一门 rc≠0 即 exit 1"钉成机检（解析该步脚本），`set -e` 断言改成与实写的 `set -uo pipefail` 一致 | ① 在 8135f1a↔28c0d2e 上复算 = 少报 31 / 新增 15（与独立复查一致）；② 变异：把该步改成只看最后一个 rc ⇒ 用例红 | `EVD-V16-29/s29_6.txt` |

## 完成定义
- 6 项全部有 EVD；本机按 `ci.yml` 顺序复跑全过；`@ci` 三绿且 `head_sha` = 交付提交。
- **普查终态**：自有源码面（不含 `.project/`）0 个文件有命中，读数由 `secret_census` 同口径脚本产生。
- opus 独立复核：S29.1 与 S29.2 各一轮，复核者自己构造反例；只输出 PASS / FAIL / UNKNOWN。
- 任何一类放宽若引起误报且两轮内消不掉 ⇒ 该类不收、留 P-41 登记，**不得为凑绿改判据**。

## 阻塞条件（遇到就停下交回规划方）
- 放宽后文档面读数有任何变化；需要动 `apps/api/app/**`；任一夹具改动导致用例数变化。
