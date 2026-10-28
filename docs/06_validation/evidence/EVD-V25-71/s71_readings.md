# EVD-V25-71 读数：`stop_all` 属主拒杀收严（P-151 甲 / D-V24-06 甲）

> 卡面：`docs/任务规划V0.25.0/steps/STEP-71-端口属主拒杀收严.md`
> 本文件只记读数与反证；判词在 `07-执行过程记录.md`。

## 1. 现状（改动前的分支顺序，`fe46206`）

| 位置 | 内容 | 问题 |
|---|---|---|
| `:127` | `if [ "$owns" != 1 ]; then` | 进入判定 |
| `:128` | `if [ "$have_ps" = 1 ]; then` | **先命中**：ubuntu runner 上 `have_ps=1` ⇒ 命令行白名单这一层永远先判 |
| `:129-133` | `case … uvicorn/next/fake_llm` | 命令行对上就**落到 kill**，即便端口属主明确不是这个 PID |
| `:134` | `elif [ -n "${ownp// /}" ]; then` | 属主拒杀 —— 只有在 `have_ps=0` 时才可达 ⇒ **在 ubuntu 上不可达** |

⇒ 「端口上有属主且 PID 不是属主 ⇒ 拒杀」这条在 CI 上从没执行过；D-V23-16 要堵的「同名的另一个会话」正好从命令行白名单漏过去。

## 2. 改动（S71.1 / S71.2 / S71.3）

`git diff --stat`：`scripts/e2e/run_real_backend.sh | 18 ++++++++++++------`（净 +5 行，只动 `stop_all` 内该分支段）。原文见 `s71_before_after.txt`。

| 项 | 改前 | 改后 |
|---|---|---|
| 分支顺序 | 命令行 → 属主 → else | **属主 → 命令行 → else** |
| 属主拒杀的形式 | `elif`（嵌在 `have_ps` 的互补分支里） | 独立 `if`，排在命令行之前 |
| 命令行白名单 | 三条（uvicorn / next / fake_llm） | **逐字未动** |
| `note:` 受限路径文案 | 原样 | **逐字未动** |
| `占用者读数` 自证行 | `:65`（注释）、`:181`、`:192` | 同三处，未删 |

## 3. 反证台（old vs new，桩替换端口/进程事实）

脚本在仓外（`D:\Code\tmp_s71_harness.sh`），做法：从 `git show HEAD:scripts/e2e/run_real_backend.sh`（old）与工作区（new）各抽出 `stop_all`（`sed` 段 + 行数/首尾锚三重守卫），再用桩替换 `role_port` / `port_owner_pids` / `port_owner` / `port_open` / `ps` / `kill`，pidfile 里放一个活着的 PID。

**case A**：属主 `99999` ≠ pidfile 里的 PID；`have_ps=1`；`ps` 返回**命中白名单**的命令行（`next/dist/bin/next start -p 3200`）——即「同名的另一个会话」形状。

```
-- old（HEAD 顺序：命令行为先）--
  [old] stopped frontend pid=563
  [old]    kills=1 recorded=[563;]
-- new（本卡顺序：属主拒杀为先）--
  [new] 跳过 frontend pid=563：端口 :3200 的监听者是 99999，不是它（不发信号）
  [new]    kills=0 recorded=[]
```

⇒ old 会**发信号**（正是 P-151 指的洞）；new **不发**，并打出属主读数。

**case B**（回归保护）：`ownp` 为空、`have_ps=0`（本机 git-bash 形状）⇒ 仍按 PID 直杀且打 `note:`，行为未变：

```
  [new_win] stopped frontend pid=563
  [new_win]    kills=1 recorded=[563;]
```

## 4. 静态判据

```
$ bash -n scripts/e2e/run_real_backend.sh
syntax ok
$ grep -c '端口 :\$port 的监听者是' scripts/e2e/run_real_backend.sh
1
$ grep -n '端口 :\$port 的监听者是' scripts/e2e/run_real_backend.sh
131:          echo "跳过 $name pid=$pid：端口 :$port 的监听者是 $ownp，不是它（不发信号）"
$ grep -c "占用者读数" scripts/e2e/run_real_backend.sh
3          ← 与改动前同数（:65 注释 / :181 红路径 / :192 绿路径）
```

拒杀行在 `:131`，命令行 `case` 在 `:134-137` 之后 —— **在命令行分支之前**（S71.2）。

## 5. 本机 `--stop` 冒烟

```
$ bash scripts/e2e/run_real_backend.sh --stop; echo "exit=$?"
note: 本机 ps 不支持 -o args=（或未取到输出）⇒ 认领只能靠端口属主，命令行特征这一层跳过
note: 本机没有 pgrep/pkill ⇒ 跳过命令行特征兜底（CI 的 ubuntu runner 有）
没有本脚本起过的进程（pidfile 不存在）
exit=0
```

（本机 `have_ps=0`，与 §3 case B 的形状一致；无栈时正常退出、不报错。）

## 6. @ci 读数

待填（本卡提交后 `e2e-real` job 的 `Stop stack` 步结论 + `E2E` 步结论见 `s71_ci.txt`）。

**判据**：`Stop stack` = success；`E2E` 步结论与改动前**相同**（本卡不得改变 e2e 结果）。改动前（`fe46206`）的 `E2E` 步结论见 `s71_ci.txt` 的 before 段。
