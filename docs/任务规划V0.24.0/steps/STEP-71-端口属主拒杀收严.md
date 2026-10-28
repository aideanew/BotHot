# STEP-71：`stop_all` 属主拒杀收严（P-151 甲）

## 1. 归属

- 所属切片：P-C 供给层
- 来源需求：`02` S-1；台账 P-151
- 来源方案：D-V24-06、D-V23-16
- 执行者：执行助手

## 2. 目标

`scripts/e2e/run_real_backend.sh` 的 `stop_all` 里，「端口上有属主且 PIDfile 里的 PID 不是属主 ⇒ 拒杀」这条分支在 ubuntu（`have_ps=1`）上也**可达**；命令行特征只在**取不到属主**时才参与判定。

## 3. 输入

- 文档：`01` §2.5、`04` §4.1（71 与 72 串行的依据）
- 契约：D-V23-16 的「端口属主为主判据」
- 前置任务：无
- 前置状态：`run_real_backend.sh:120-132` 现读分支顺序见下

## 4. 输出

- 修改：`scripts/e2e/run_real_backend.sh`（仅 `stop_all` 内 `:122-135` 一段）
- 新增：`docs/06_validation/evidence/EVD-V24-71/`

## 5. Execution Steps

1. [ ] 先贴现状（供 before/after）：

   ```
   :120  if [ -n "${ownp// /}" ] && printf '%s\n' "$ownp" | grep -qx "$pid"; then owns=1; fi
   :122  if [ "$owns" != 1 ]; then
   :123    if [ "$have_ps" = 1 ]; then          ← 先命中
   :124-127   命令行白名单（含 next-server）
   :128-131  elif [ -n "${ownp// /}" ]; then   ← 永远到不了
   :132-134  else note
   ```

2. [ ] **S71.1** 把「有属主且非属主 ⇒ 拒杀」提到最前，改成独立的 `if` 而非 `elif`：

   ```sh
   if [ "$owns" != 1 ]; then
     if [ -n "${ownp// /}" ]; then
       # 端口上确有监听者，且不是 PIDfile 里这个 PID ⇒ 它已被复用，一律不发信号。
       # 命令行不参与：命令行特征分不清「同名的另一个会话」，那正是 D-V23-16 要堵的洞（D-V24-06 甲）。
       echo "跳过 $name pid=$pid：端口 :$port 的监听者是 $ownp，不是它（不发信号）"
       continue
     fi
     if [ "$have_ps" = 1 ]; then
       ...（命令行白名单，原样保留）
     else
       echo "note: $name pid=$pid 无端口属主证据也无 ps 能力 ⇒ 按 PID 直杀（本机能力受限，非静默）"
     fi
   fi
   ```

3. [ ] **S71.2** 确认命令行分支现在只在 `ownp` 为空时可达（读 diff 自证）
4. [ ] **S71.3** `占用者读数` 那行日志**不得删**（P-148 的自证行，是本卡唯一的现场证据来源）
5. [ ] `bash -n scripts/e2e/run_real_backend.sh` 语法检查
6. [ ] 本机跑一次 `bash scripts/e2e/run_real_backend.sh --stop`（无栈时也应正常退出，不得报错）
7. [ ] 本卡单独提交并推送；`@ci` 的 `Stop stack` 步必须仍 success
8. [ ] 写证据：before/after 的 `sed -n '118,140p'` 原文 + `Stop stack` 步的 @ci 日志片段

## 6. 验收标准

- [ ] `bash -n` 通过
- [ ] `grep -c '端口 :\$port 的监听者是'` = 1，且该行在命令行分支**之前**
- [ ] `grep -c "占用者读数"` 与改动前同数（未被删）
- [ ] `@ci` 的 `Stop stack` 步 = **success**
- [ ] `@ci` 的 `E2E` 步结论与改动前**相同**（本卡不得改变 e2e 结果）
- [ ] 本机 `--stop` 退出码 0
- [ ] 反证可达性：证据里必须写清「在 ubuntu 上，属主非本 PID 时会走拒杀分支」的**代码路径证明**（`sed` 原文），不要求本机实跑（本机无 `ss`/`lsof`）

## 7. 验证命令

```bash
cd /d/Code/AideanBotHot
bash -n scripts/e2e/run_real_backend.sh && echo "syntax ok"
sed -n '118,142p' scripts/e2e/run_real_backend.sh
grep -n "占用者读数" scripts/e2e/run_real_backend.sh
bash scripts/e2e/run_real_backend.sh --stop; echo "exit=$?"
```

## 8. 证据路径

`docs/06_validation/evidence/EVD-V24-71/`

## 9. 允许修改

- `scripts/e2e/run_real_backend.sh`（**仅** `stop_all` 内该分支段）
- `docs/06_validation/evidence/EVD-V24-71/**`

## 10. 禁止修改

- `run_real_backend.sh` 的其它任何段（启动、端口检查、`port_owner_pids` 实现）
- `apps/**`、`packages/**`、`docs/任务规划V0.12.0/contracts/**`
- 不得为了「让反证可跑」而在本机装 `ss`/`lsof` 或改脚本去适配 Windows

## 11. 依赖与阻塞

- Depends on：无
- Blocks：**STEP-72**（两者同改 `run_real_backend.sh`，必须串行；取 71 先 72 后）
- 阻塞条件：改完后 `Stop stack` 从 success 变红 ⇒ 停手回退，登 P 号。**这说明 ubuntu 上 `ownp` 含的不是 PIDfile 里的 PID**，那是一个比本卡更大的事实，必须交回规划方

## 12. 建议执行档位

sonnet。理由：分支重排，约 5 行。

## 13. 升级条件

- `Stop stack` 变红 ⇒ 升级 opus 并停手（见阻塞条件）
- 发现 `port_owner_pids` 在 ubuntu 上返回多值（同一端口多个监听者）⇒ 升级，交回规划方

## 14. 预估规模

小，≈0.2 人日，小于 2 小时。

## 15. 熔断

同一判据 2 轮未过 ⇒ 停手，登 P 号。

## 16. 交接物

`EVD-V24-71/` 要能让一周后的人只看 `sed` 原文就判断「拒杀分支是否在命令行之前」。
