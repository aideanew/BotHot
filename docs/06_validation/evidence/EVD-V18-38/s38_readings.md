# EVD-V18-38 · STEP-38 安全门输入与重试

> 基线 `main@9591980`（STEP-39 收口批）｜版本 V0.18.0｜队列第四项
> 归属 Agent-Guard｜来源 P-55、P-77｜裁决 D-V18-12、D-V18-13
> §13 禁止面（漏洞阈值与豁免清单）本批**一行未动**，并由常驻用例钉住（见 §4.3）

## 0. 本批改动面（对照卡面 §7/§12）

| 文件 | 改动 |
|---|---|
| `.github/workflows/security.yml` | ① 的扫描输入换成 `uv.lock` 导出清单；四步统一经 `scripts/security_scan.py` 执行（一次重试 + "未运行"判定）；④ 的 rc 改由 status 文件回传；artifact 上传面加输入清单与三份 status；新增 `UV_VERSION` 钉版 |
| `scripts/security_scan.py` | 新增（卡面 §7「可能的辅助脚本」） |
| `apps/api/tests/test_security_scan_helper.py` | 新增 13 用例 |
| `docs/06_validation/evidence/EVD-V18-38/` | 本目录 |

## 1. 开工读数（现读锚 = `9591980`）

- `.github/workflows/security.yml` 就是卡面说的"或现名"，四道门齐（`① pip-audit / ② pnpm audit / ③ trivy / ④ gitleaks`）✓
- ① 旧形状的输入是**当场解析出来的环境**：`pip install -e ".[dev]"` 之后 `pip-audit` 不带 `-r`
  ⇒ 同一提交在两台机器可装出不同版本（`pyproject.toml` 主依赖 15 条里 14 条是 `>=` 区间，
  唯一不带约束的是 STEP-32 刚加的 `tzdata`）
  ⇒ 这正是 P-55 说的那件事。
- ② 已经是锁锚定的：`pnpm install --frozen-lockfile` + `pnpm audit --prod` ⇒ S38.1 的"确认"通过，无需改造
- ③④ 不是依赖解析器（③ 扫文件树、④ 扫 git 历史）⇒ D-V18-12 的"锁文件为唯一依赖真相"对它们只落到
  ③ 读到的清单文件上，本卡不把它们改成"只读锁"，那会削掉 misconfig/secret 两维（是倒退）
- `gitleaks` 本机在 `%LOCALAPPDATA%\Programs\tools\gitleaks\gitleaks.exe`（8.21.2，与 CI 同版本）：
  实测**零检出时仍写出 `[]` 报告**（3 字节）⇒ "报告存在与否"能当判据用，不会把"干净"误判成"没跑"
- `uv export --frozen --extra dev --no-hashes --no-annotate --no-emit-project`（uv 0.13.5）本机实跑 ⇒ 65 个钉版条目
- `pip-audit==2.10.1`（与 CI 同版本，装在仓库外用户站点）读这份清单实跑 ⇒
  rc=0、报告 3514 字节、`No known vulnerabilities found`，并接受清单里的平台标记行

## 2. S38.1 四道门的输入表

| 门 | 扫描输入（改后） | 输入从哪来 | 阻断线（**未动**） |
|---|---|---|---|
| ① pip-audit | `apps/api/requirements-from-lock.txt`（65 条 `==` 钉版，含 dev extra） | `uv export --frozen …` 从 `apps/api/uv.lock` 导出；`pip-audit -r … --no-deps`（闭包已在锁里） | 有 `fix_versions` ⇒ BLOCK；无 ⇒ 🟡 WARN |
| ② pnpm audit | 由 `pnpm install --frozen-lockfile` 落出的树 + registry 建议，`pnpm audit --prod --json` | `apps/web/pnpm-lock.yaml`（本就是锁锚定，本卡只加"报告在不在"的判定） | `critical`/`high` ⇒ BLOCK |
| ③ trivy fs | 仓库文件树，排除 `SCAN_EXCLUDES`（`.project` 等 86.7% 的第三方源码在内） | 文件系统：清单文件（含两份锁）、Dockerfile、compose | 依赖需 `Severity∈{CRITICAL,HIGH}` **且** 有 `FixedVersion`；misconfig 只看严重度；secret 一律 BLOCK |
| ④ gitleaks | git 全历史（`fetch-depth: 0`）+ 仓库内 `.gitleaks.toml` 规则与白名单 | 仓库历史本身 | `rc=1` ⇒ BLOCK；其他非 0 ⇒ SCANNER_ERROR；`rc=0` ⇒ OK |

四份输入与其 status 文件都进了 `security-reports` artifact（旧版只留报告，输入清单无处复核）。

## 3. S38.2 重试与"扫描器未运行"

`scripts/security_scan.py` 三条判据（写进模块 docstring，逐条有常驻用例）：
1. **换不来结论才算没跑成**：报告缺失或 0 字节 ⇒ 重试一次；两次都没有 ⇒ `scanner_error`。
   "检出漏洞"（rc 非 0 但报告在）**不是**失败——裁决权仍在末尾汇总门禁。
2. **每轮开始前删掉上一轮的报告**：不删就会有一种偏绿的假绿——上一批残留 / 上一轮崩在半路的残缺文件
   被这一轮读成"报告存在"。
3. **重试次数写死 2**：无限重试会把"这个环境跑不成"伪装成"跑得慢"，最后由 30 分钟 job 超时收场且没有原因。

`--status-file` 的存在理由：④ 的判据要看**最后一轮的 rc**（0 干净 / 1 检出 / 其他 工具坏）。
包一层重试之后若不把这个码交回来，消费侧就只能靠猜——那是把一条已有机检改回盲判。

### 3.1 本机反证读数（真实工具，不是假 runner）
`pip-audit --no-such-flag …`（即卡面要的"故意给错扫描器参数"）：
```
[pip-audit] 第 1/2 次：rc=2 报告字节=0（无报告 ⇒ 这一轮没跑出结论）
[pip-audit] 没有报告 ⇒ 3.0s 后重试一次
[pip-audit] 第 2/2 次：rc=2 报告字节=0（无报告 ⇒ 这一轮没跑出结论）
[pip-audit] 判定=scanner_error ⇒ 扫描器未运行：pip-audit 连试 2 次都没有产出报告文件（最后一轮 rc=2），
                                    本维**没有终判**——既不是「发现漏洞」也不是「没有漏洞」
helper rc=1
```
还原（去掉那个假参数、加回 `--no-deps` 等正确参数）⇒ `判定=ran`、报告 3514 字节、helper rc=0。
CI 侧同一对反证见 §5（推送读数）。

## 4. 常驻用例的覆盖面（13 条，全部不依赖网络与 CI）

1. 首轮跑成 ⇒ 不重试（断言 `sleep` 一次都没被调用——只断言 rc 会放过"每次都重试"的实现）。
2. 首轮没跑成、次轮跑成 ⇒ 恰好重试一次，且 `tries` 两轮的字节数分别记着。
3. 两轮都没有 ⇒ `scanner_error` + 原因以「扫描器未运行」开头 + 最后一轮 rc 可取。
4. **极性：rc=1 且报告在 ⇒ ran**（"发现漏洞"不许被读成"工具坏"）。
5. 0 字节报告 ⇒ 与"没有"同权。
6. **磁盘上本来就有旧报告 ⇒ 判未运行**（判据 2 的正身，也是最容易被实现漏掉的一发）。
7. status 文件往返（name/status/last_rc）。
8. CLI 没给命令 ⇒ `scanner_error` 且写 status 文件（消费侧不必区分"忘了传"与"跑不成"）。
9. CLI 真子进程一发：写报告的命令 ⇒ 0；什么都不写的命令 ⇒ 1（验 `--` 之后的 argv 原样传递）。
10. 四步都接了 helper（`scripts/security_scan.py` 出现 4 次 + 每步仍先写 `SCANNER_ERROR`）。
11. ① 的输入来自锁文件（含"旧形状没回来"的**按行**判据——整文件搜会把解释旧做法的那条注释也算进去）。
12. §13 禁止面守卫：空豁免基线、两个 HIGH 集合、trivy 的"有 FixedVersion 才阻断"、汇总门禁四个裁决位。
13. `ATTEMPTS == 2` 与 `--help` 可跑。

### 4.1 写用例时踩到自己的一条
第 11 条第一版写成"整个 yml 里不许出现 `pip install -e ".[dev]"`"——**而本卡自己在那条注释里
引用了旧命令**，于是永远红。改成逐行剥注释再判。这条留在这里，是因为它属于"判据被自己的
解释文字绊倒"那一族：判据文本与被判对象必须分层。

## 5. CI 读数（待回填：交付批 / 反证批 / 还原批）
- 交付批 head：待回填（Security 四步日志里的 `第 1/2 次 … 判定=ran` 与 `扫描输入 requirements-from-lock.txt：N 个钉版条目`）
- 反证批：待回填（Security 必须红，且原因行含「扫描器未运行」；CI / CI-Windows 仍绿）
- 还原批：待回填（三绿）
