# EVD-V5-00S — Security 回绿：gitleaks 逐指纹登记 + HEAD 打码 + mako 版本

执行机：**`@win`**（Windows 10.0.19045）；gitleaks **8.21.2**（与 `security.yml:53` 同版，本机自装）
基线：`main@6764ebe`（00X 前的规划提交）；扫描域：本仓库 git 全历史（**156 commits scanned**）
依据：D-V4-04（指纹只由真实 gitleaks 产出、禁猜、禁重写历史）、D-12（逐指纹，禁整目录/整文件豁免）

## 1. 改动清单

| 文件 | 动作 | 对应三级任务 |
|---|---|---|
| `.gitleaksignore` | 新建，11 条指纹 + 每条上方注释（是什么/为何非真实凭据/来源提交） | S0S.2.1、S0S.2.2 |
| `docs/06_validation/evidence/EVD-V2-00R/out_evidence_check.txt` | 第 137 行的夹具 DSN 去形 + 文末脱敏补记 | S0S.1.4 |
| `apps/api/uv.lock` | mako `1.4.1 → 1.4.2`（3 行：version/sdist/wheel），镜像 URL 与 sha256 均来自真索引 | S0S.3.1 |
| `docs/06_validation/evidence/EVD-V2-02/prove_anchor_fallback.py` | **不改**（并发会话路径，硬规则第五节优先于卡面 S0S.1.2） | S0S.1.2 → 以指纹登记替代 |

## 2. 指纹来源与两机对账（D-V4-04 的可证性）

```
# 本机（@win, gitleaks 8.21.2, git 模式）
$ GIT_ATTR_NOSYSTEM=1 gitleaks detect --source . --config .gitleaks.toml -f json -r gl_win2.json
156 commits scanned / 8 leaks found            → 8 条指纹

# V0.10.0 那台 Linux 机器（同版 8.21.2，见 任务规划V0.10.0/evidence/81cb997/gitleaks_fingerprints_81cb997.txt）
11 条指纹
```
对账结果：**本机 8 条与 V0.10.0 的 8 条逐字符串相同**（同一 commit:file:rule:line）；
差集 = 3 条，全部来自 `798f2638…`（`adr-0010` 草稿、`current-plan.md:796`、`TASK-004.md:21`）。
处置：按卡面"以 CI artifact 为准、取并集"⇒ `.gitleaksignore` 写 **11 条**。

### 为什么本机扫不到那 3 条（未解，如实记）
本机 `git rev-list --count HEAD` = **165**，而 gitleaks 报 **156 commits scanned**（差 9）。
差的那 3 条恰在 `798f263` 一族，怀疑与本机 clone 的引用状态或 merge 计数有关，**没有证据前不下结论**；
影响面：并集已经覆盖两边全部命中，Security 门禁在 CI 上按 CI 自己的扫描域判定，本机少扫几条不会造成假绿放行。

## 3. 生效性正反证（.gitleaksignore 不是装饰）

```
# 正证（有文件）
$ GIT_ATTR_NOSYSTEM=1 gitleaks detect --source . --config .gitleaks.toml
INF no leaks found                              RC=0

# 反证（把文件移开，必须复现全部命中——R-5 的判据）
$ mv .gitleaksignore .staging/gi.bak && gitleaks detect --source . --config .gitleaks.toml
WRN leaks found: 8                              RC=1
$ mv .staging/gi.bak .gitleaksignore
```
⇒ 豁免是**逐指纹**生效的（8→0→8），不是一刀切关掉扫描。注释行不破坏解析（gitleaks 8.21.2 实测可带 `#` 行）。

## 4. Windows 侧的一个真缺陷：workspace 模式在 @win 不可用

```
$ gitleaks detect --no-git --source . --config .gitleaks.toml -f json
scan completed in 3m26s / WRN leaks found: 507     ← 全在 .project/**（vendored LangBot/firecrawl）
```
原因：`--no-git`（工作树模式）给出的路径是 Windows 反斜杠形式（`.project\LangBot\…`），
而 `.gitleaks.toml` 的全局/规则 `paths` 写的是 POSIX 斜杠（对整条路径做 regex search）⇒ **allowlist 全部失配**，
vendored 子树被当作命中。CI 走 git 模式（路径来自 git，恒为 `/`），所以 CI 不受影响。

结论与处置：
- 本卡的 S0S.1.3「本地 `--no-git` 对工作树 0 命中」在 @win **不能作为判据**（它测的是路径分隔符，不是密钥）。
  替代判据（已跑）：git 模式 0 命中 + 仓库自带的 `secret_shape_scan.py`（stdlib、跨平台）对 `docs/任务规划V0.11.0` 与
  `docs/03_solution/decisions` HIGH **0**。
- 已把该缺陷写进 `cross-platform.md` 待办面：若将来要在 Windows 本地跑工作树模式，需给 `.gitleaks.toml` 的 paths
  加 `[/\\]` 形式的分隔符兼容（属改扫描域，必须先在 CI 上正反证一次，故本卡不做）。

## 5. mako 的审计口径：uv.lock 不是 pip-audit 的输入

- `security.yml` ① 的做法是 `pip install -e ".[dev]"` 后 `pip-audit`（审的是**真实装出来的环境**，不是锁文件）。
  本机 venv 实测：`pip index versions mako` → 1.4.3 可用，**已装 1.4.3** ⇒ pip-audit 侧本来就不会报 1.4.1。
- 那 1.4.1 是谁报的？`security.yml` ③ trivy 的 **fs 扫描会读锁文件**，uv.lock 里钉着 1.4.1 ⇒ 改 uv.lock 才是有效动作。
- **没有用 `uv lock --upgrade-package mako`**：实测它会把整个锁重解析（1379 插入 / 1161 删除），
  把索引源从 `pypi.tuna.tsinghua.edu.cn` 换成 `files.pythonhosted.org`，并顺带新增
  prometheus-client / pytest-cov / tomli 三条解析项。那不是"升级一个包"，是换掉全仓依赖来源，
  属"影响面大且难复核"的改动 ⇒ 改用手抄 3 行（版本 + 两个 URL + 两个 sha256 + size + upload-time），
  每个字段都有出处：URL/sha256 取自镜像 simple 索引，sha256 与本机下载件的计算值**逐位相同**，
  upload-time 取自 PyPI JSON（`2026-09-22T20:40:55.060882Z` / `…56.423830Z`）。

## 6. 顺带验出的一个既存事实：uv.lock 早已与 pyproject 不同步

```
# 原始锁（HEAD 版）
$ uv lock --check      → RC=1  "The lockfile at `uv.lock` needs to be updated"
# 我这 3 行改完之后再跑
$ uv lock --check      → RC=1  同样
```
⇒ **陈旧状态在我改之前就存在**（对照实验两次都红），不是我引入的。
差异内容：`prometheus-client`、`pytest-cov`、`tomli` 在 pyproject 里有声明但锁里没有解析项。
这条不属于 00S（不改门禁语义、不在安全卡里夹带依赖重构），已另立待办：见 05 §2 未决 U-19。

## 7. 未做 / 阻塞

| 项 | 状态 | 原因 |
|---|---|---|
| S0S.3.2 `uv sync` + 全量 pytest 不回归 | 🛑 @win 不做 | 本机无 PG/Redis，且全量 pytest 在本机 stall（EVD-V5-00X §4.1）；连库与全量按 D-V4-01 由 `@ci ubuntu` 出读数 |
| S0S.3.3 推送后 Security run = success | ⚪ 待 push + CI 读数 | 本机无 `gh`，认定需按 D-V6-02 取 GitHub REST 原始响应；私有仓库需只读 token（属外部凭据） |
| S0S.1.2 改 prove_anchor_fallback.py | ❌ 不执行 | 并发会话路径；已用逐指纹登记覆盖同一条命中，门禁效果等价 |
