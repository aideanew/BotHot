# STEP-00S Security回绿-gitleaks与依赖告警

> 基线 main@61358c3｜状态：🔴 门禁失败、待修

| 字段 | 内容 |
|---|---|
| 1 归属（执行者） | 执行Agent |
| 2 验收者（与执行者分离） | 规划方(Hark)，只输出 PASS/FAIL/UNKNOWN |
| 3 难度 / 里程碑 | 中 / M0 |
| 4 来源 | F-09/F-10/F-11；D-V4-02/03 |
| 5 目标 | Security run 阻断项 0；且新增文件不再引入凭据形。 |
| 6 输入 | security.yml:420-531；.gitleaks.toml；8 处命中清单（evidence/61358c3/ci_security_61358c3.txt） |
| 7 输出路径 | .gitleaksignore；docs/任务规划V0.7.0/06-入库与双端一致.md（打码 1 行）；docs/06_validation/evidence/EVD-V2-02/prove_anchor_fallback.py（打码 1 行）；apps/api/uv.lock |
| 8 三级任务 | 见下 |
| 9 验收 | Security workflow success；gitleaks HEAD+历史 0；Trivy 不再报 mako |
| 10 命令 | `gitleaks detect -s . ; gitleaks detect --no-git -s . ; cd apps/api && uv lock --upgrade-package mako` |
| 11 证据 | docs/任务规划V0.8.0/evidence/61358c3-00s/ |
| 12 允许修改 | 上述 4 个路径 |
| 13 禁止修改 | 不重写 git 历史；不降 SECURITY_GATE_ENFORCE；不改 security.yml 判定逻辑 |
| 14 依赖 / 阻塞 | 无（与 00C 文件不重叠，可并行） / 无 |
| 15 档位 | T2 |
| 16 升级条件 / 规模 | 若历史命中中有真实凭据（非占位）⇒ 立即停，报规划方与用户轮换密钥（scripts/rotate_keys.sh），不得仅 allowlist / ≈0.5 人日 |

## 三级任务

### S00S.1 HEAD 内打码
- **S0S.1.1** V0.7.0/06:46 的 DSN 示例改为 `postgresql+psycopg://<user>@<host>/<db>` 无口令形
- **S0S.1.2** prove_anchor_fallback.py:556 的 `key = "..."` 改为非密钥形变量名或从环境读取，判据行为不变
- **S0S.1.3** 本地 `gitleaks detect --no-git -s .` 对 HEAD 工作树 0 命中

### S00S.2 历史指纹登记
- **S0S.2.1** `gitleaks detect --report-format json` 取 8 条 Fingerprint（commit:file:rule:line）
- **S0S.2.2** 写入 `.gitleaksignore`，每行上方注释：占位口令/测试样本、非真实凭据、来源提交
- **S0S.2.3** 全历史扫描 0 命中；确认 `.gitleaksignore` 被 workflow 读取（gitleaks 默认读取仓根）

### S00S.3 依赖告警
- **S0S.3.1** `uv lock --upgrade-package mako` 至 ≥1.4.2
- **S0S.3.2** `uv sync` + 全量 pytest 不回归
- **S0S.3.3** 推送后 Security run = success，阻断 0、告警 ≤2

## 执行记录（V0.11.0 第二增量 · 2026-10-15 · @win + gitleaks 8.21.2 本机自装）
读数与对账在 `docs/06_validation/evidence/EVD-V5-00S/security_gitleaks_mako.md`。

| 三级任务 | 状态 | 事实 |
|---|---|---|
| S0S.1.1 V0.7.0/06:46 去形 | ✅ 已在前一轮完成 | 本轮核对该行：worktree 内容已无凭据形；历史形态由指纹登记覆盖 |
| S0S.1.2 改 prove_anchor_fallback.py | ❌ **不执行，偏离卡面** | 该路径属并发会话（硬规则第五节优先）；同一条命中改为逐指纹登记，门禁效果等价 |
| S0S.1.3 本地 `--no-git` 工作树 0 命中 | ❌ **判据在 @win 不成立** | 工作树模式给反斜杠路径，`.gitleaks.toml` 的 POSIX 斜杠 allowlist 全失配 ⇒ 507 条 vendored 假命中。替代判据：git 模式 0 命中 + `secret_shape_scan` HIGH 0 |
| S0S.1.4 `out_evidence_check.txt:137` 打码 | ✅ | 夹具 DSN 去形 + 文末脱敏补记（断言含义不变） |
| S0S.2.1 取指纹 | ✅ | 本机 git 模式 **156 commits / 8 leaks**；与 V0.10.0 的 11 条对账：8 条逐字符串相同，差 3 条来自 `798f263` |
| S0S.2.2 写 `.gitleaksignore` | ✅ | 并集 **11 条**，每条上方注释"是什么/为何非真实凭据/来源提交"；D-12 逐指纹，无目录级豁免 |
| S0S.2.3 全历史 0 命中 + 生效性 | ✅ | 有文件 → `no leaks found` rc=0；移开 → `leaks found: 8` rc=1；恢复 → 0（正反证都跑了） |
| S0S.3.1 mako ≥1.4.2 | ✅ **但不是用 uv 做的** | `uv lock --upgrade-package mako` 实测重解析全锁（1379/1161 行、换索引源、新增 3 包）⇒ 改手抄 3 行，URL/sha256/size/upload-time 均有出处（镜像 simple 索引 + PyPI JSON + 本机下载件校验） |
| S0S.3.2 `uv sync` + 全量 pytest | 🛑 @win 不做 | 无 PG/Redis，且全量 pytest 在本机 stall（05 U-20）；按 D-V4-01 由 `@ci ubuntu` 出读数 |
| S0S.3.3 Security run success | ✅ **达成** | run `38688133682` completed/success，head_sha `d2462e2b`；①pip-audit ②pnpm audit ③trivy ④gitleaks 与汇总门禁逐步 success（原始响应存 EVD-V5-00S/同级 evidence）。本机无 `gh`，用未认证 REST 取证——本仓库是 public，不需要向用户要 token |

顺带查实的一件事（写进 05 U-19）：**`uv.lock` 早就与 `pyproject.toml` 不同步**
（`prometheus-client`/`pytest-cov`/`tomli` 有声明无解析项），对照实验证明在我改锁**之前** `uv lock --check` 就是 RC=1。
不在安全卡里夹带依赖重解析。


## V0.9.0 → V0.10.0 本卡变更（基线 main@81cb997）

- **阻塞解除**：本机有 gitleaks **8.21.2**（与 security.yml:53 同版），V0.9.0『不猜指纹、本机无二进制』这一 BLOCKING 消失；全历史指纹 11 条已产出（E-gitleaks）。
- **新增 S0S.1.4**：HEAD 工作树仍含 `EVD-V2-00R/out_evidence_check.txt:137` 的占位口令 DSN（已跟踪）⇒ 先打码，再登记历史指纹。
- **对账**：本机全历史 11 条 vs 61358c3 时 CI 报 8 条，差额 3 条全来自 `798f263`（ADR-0010 草稿、current-plan、TASK-004）。以 CI 的 `gitleaks.json` artifact 为准；两者并集写入 `.gitleaksignore`，每行附『占位、非真实凭据』注释。
- 剩余 10 项（9 + S0S.1.4）。连续 4 次 Security 红（E-ci），这是 M0 唯一硬红。

## 裁决已签（V0.11.0 第四节第 2 步 · 2026-10-15 12:04）
| 项 | 变化 |
|---|---|
| D-V4-04 | 已签 A：指纹**只由真实 gitleaks 8.21.2 产出**（本机安装或 CI 产物均可），禁猜指纹、禁重写历史；按 D-12 逐条登记 `.gitleaksignore`，目标 Security 工作流转绿 |
| 验收面 | 本卡 Done 只能由 `@ci` **ubuntu-latest** 判定；`@win` 读数只算开发烟测，`@linux` 为依赖机本地验证 |
| 标签 | 依 D-V6-01，本卡 `@dep` 已全部改写为 `@linux`/`@ci` |
