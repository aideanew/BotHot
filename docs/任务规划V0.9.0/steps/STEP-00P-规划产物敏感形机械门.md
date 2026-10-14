# STEP-00P 规划产物敏感形机械门（V0.9.0 新增）

| 字段 | 值 |
|---|---|
| 归属-切片 | S-M0.5 执行治理 |
| 归属-需求 | REQ-NF-002（安全）、M-7（判据有效性） |
| 归属-方案 | 本版 01 F-09、04 §4；V0.8.0 F-10（记录 `f70d52f` 引入 1 处新增命中）与 G-PLAN（口头门，无机器） |
| 里程碑 | M0.5 |
| 档位 | haiku/T1　理由：改一个 Makefile 步 + 立一条纪律，机械动作；不含裁决。**升级条件**：若需要改 `.gitleaks.toml` 规则本身 ⇒ opus（安全门禁语义变更） |
| 规模 | 小（≈0.25 人日） |
| 依赖 | Depends on：无　Blocks：STEP-12（发布前必须过此门） |
| 基线 | main@53ebc4a |
| 剩余原子任务 | 5（👤 0） |
| 状态 | 🟡 本轮已手工做过一次（F-09），缺机器化 |

## 目标（可验证的一句话）
规划/证据类文档入库前，敏感形扫描成为 `make evidence-check` 的**阻断步**：命中 >0 即红，缺 gitleaks 时打印 `SKIP(tool missing)` 并以非 0 退出区分——从而不再出现"防凭据入库的文档自己带凭据形"。

## 输入
- 事实：`evidence/53ebc4a/static_readings_53ebc4a.txt` S-05；V0.8.0 F-10
- 已存在的工具：`docs/任务规划V0.5.0/evidence/65f508b/secret_shape_scan.py`（复刻 `.gitleaks.toml` 规则 1 + 已知 token 前缀 + 私钥块，带占位值 ALLOW 白名单，CLI 为 `<目录>`）
- 现状实测：`V0.7.0` HIGH 0（43 文件）、`V0.9.0` HIGH 0（36 文件）、`V0.6.0` HIGH 5（全在被排除的 `STEP-R0+00C_combined_simulated_a9b194d.patch`）

## 输出（文件）
`Makefile`（`evidence-check` 内新增一步）、`docs/04_engineering/conventions.md`（增一条）、`docs/06_validation/evidence/EVD-V4-00P/`

## Execution Steps
1. [ ] 🛠 **S00P.1.1** `evidence-check` 增步：对本次待提交路径跑 `secret_shape_scan.py`，HIGH>0 ⇒ 目标失败；二进制缺失 ⇒ 打印 `SKIP(tool missing)` 且以非 0 退出（不静默 PASS）
   - S00P.1.1.1 扫描范围取自 `git diff --cached --name-only`，**不扫全仓**（全仓会被历史遗留件反复挡，导致门被人关掉）
2. [ ] 🔴 **S00P.1.2** 反证电池：临时写一个含占位 DSN 的 `.md` 到待提交列表 ⇒ 门必须红；删掉 ⇒ 必须绿
3. [ ] 📄 **S00P.2.1** 立规：**文档内不得内联敏感形字面量或扫描正则本身**；要写判据就指向脚本。理由写清是本仓自伤两次的实测（V0.7.0/06 抄占位 DSN、又抄正则）
4. [ ] 🛠 **S00P.2.2** 给"必须引用某条凭据形"的场景定替代写法：只描述形状 + 指向 `secret_shape_scan.py` + 权威以 `gitleaks git --log-opts=origin/main` 为准
5. [ ] ✅ **S00P.3.1** 明确本门的**边界声明**（写进 conventions 与卡面）：近似器不替代上游默认规则/熵判据；历史提交里的指纹不会因工作树打码而消失，仍需 `.gitleaksignore` 逐指纹登记（归 00S，不并入本卡）

## 验收标准
- [ ] `make evidence-check` 含该步且对当前待提交路径 rc=0
- [ ] S00P.1.2 的两档反证读数入 EVD（红档与绿档各一次，且是本轮现跑）
- [ ] `SKIP(tool missing)` 路径存在且**非 0 退出**（判据可复跑）
- [ ] conventions 增条，含"不内联敏感形"与"近似器边界"两句
- [ ] 本卡未改 `.gitleaks.toml` 规则、未自建 allowlist

## 验证命令
```bash
make evidence-check 2>&1 | tail -15; echo rc=$?
python docs/任务规划V0.5.0/evidence/65f508b/secret_shape_scan.py docs/任务规划V0.9.0 | tail -2
python docs/任务规划V0.5.0/evidence/65f508b/secret_shape_scan.py docs/任务规划V0.7.0 | tail -2
grep -n 'secret_shape_scan' Makefile
```

## 证据路径
`docs/06_validation/evidence/EVD-V4-00P/`

## 允许修改
`Makefile`（仅 `evidence-check` 步骤体）、`docs/04_engineering/conventions.md`、EVD-V4-00P
## 禁止修改
`.gitleaks.toml`（规则语义变更需单独评审）、`docs/任务规划V0.1.0…V0.8.0/**`（历史规划不改写）、`apps/**`、`packages/**`、`.gitleaksignore`（归 00S，需真实指纹）

## 依赖与阻塞
- Blocks：STEP-12　Depends on：无
- 阻塞条件：① 若门一开就把所有历史遗留件挡死 ⇒ 说明扫了全仓而非待提交集，改范围而不是关门；② 若需要豁免才能过 ⇒ 停下上报 00S，本卡不得自建 allowlist

## 建议档位 / 升级 / 规模
`haiku/T1`；触及规则语义 ⇒ `opus`；小，≈0.25 人日。
