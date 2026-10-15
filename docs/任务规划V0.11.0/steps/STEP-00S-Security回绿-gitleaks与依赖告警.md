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

## V0.9.0 → V0.10.0 本卡变更（基线 main@81cb997）

- **阻塞解除**：本机有 gitleaks **8.21.2**（与 security.yml:53 同版），V0.9.0『不猜指纹、本机无二进制』这一 BLOCKING 消失；全历史指纹 11 条已产出（E-gitleaks）。
- **新增 S0S.1.4**：HEAD 工作树仍含 `EVD-V2-00R/out_evidence_check.txt:137` 的占位口令 DSN（已跟踪）⇒ 先打码，再登记历史指纹。
- **对账**：本机全历史 11 条 vs 61358c3 时 CI 报 8 条，差额 3 条全来自 `798f263`（ADR-0010 草稿、current-plan、TASK-004）。以 CI 的 `gitleaks.json` artifact 为准；两者并集写入 `.gitleaksignore`，每行附『占位、非真实凭据』注释。
- 剩余 10 项（9 + S0S.1.4）。连续 4 次 Security 红（E-ci），这是 M0 唯一硬红。
