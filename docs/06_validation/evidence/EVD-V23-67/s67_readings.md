# EVD-V23-67 STEP-67 读数与判词（e2e-real 基线清污）

> 基线 main@`2f4b115`（STEP-60 探针批）｜裁决 D-V23-15、D-V23-16（本批代录入档，126→133 行）
> 卡面 `docs/任务规划V0.23.0/steps/STEP-67-e2e-real基线清污.md`（内容由规划方 2026-10-28 指令原文给出，执行侧代录成文件并逐条核字节）
> 一句话：**67 不改产品，只把"未登录访问受保护页"的两档落点差异登记成契约，并把"该杀哪个进程"的判据从命令行特征换成端口属主。**

---

## 1 交付面（两处产品外字节 + 零产品字节）

| 文件 | 改了什么 | 卡面第 6 格 |
|---|---|---|
| `scripts/e2e/run_real_backend.sh` | ① `stop_all` 的认领判据换成"是不是该角色端口的监听者"（新 `port_owner_pids()` / `role_port()`），命令行特征降为**辅助**并加 `*"next-server"*`；② `have_ps` 从"探存在"改成"探能力"（`ps -p 1 -o args=` 真有输出才算 1）；③ 端口终检**无条件**落一行属主读数（空闲时 `(空)`） | ✅ 明列该文件 |
| `apps/web/e2e/admin.spec.ts` | 只改 ①：抽成 `expectGuestLanding(page, path)`，mock 分支**断言一字未改**，real 分支按 D-V23-15 的四条不变量 + 附 `guest-landing-*.txt` 物证；文件头注补一段"两档落点不同是已登记的构建差异" | ✅ 明列"仅 ①" |
| 产品字节 | **零改动**（`middleware.ts`、`components/**`、`lib/**`、`apps/api/app/**`、`packages/contracts/**` 全不碰） | ✅ 第 7 格 |

## 2 规划方任务书里两条**按字面不可满足**的判据（按意图实现，不静默改判据）

| 判据原文 | 字面问题 | 本批怎么做 |
|---|---|---|
| 验收 ③「`frontend` 的 `E2E (mock UI)` 仍 **42 passed**」 | 现读 mock 档是 `31 passed / 11 skipped`（42 条**被收集**，11 条是 real-only）。"42 passed" 从来不成立，v1.1.4 起就是 31/11 | 按"同集 42 条、0 failed、passed/skipped 拆分与基线一致"判；本批实测 `31 passed / 11 skipped / e2e_rc=0`，与 `c13dbd4` 后完全同数 ⇒ 无误伤 |
| 验收 ②「`Stop stack` = success，**且日志里仍能看见 `占用者读数` 那一行**」 | 原实现只在**红路径**打印该行 ⇒ success 时永远看不到，两条子句互斥 | 终检改成**无条件**读一次属主并落行（空闲打 `(空)`），两半同时成立；顺带满足"事后能证明读数没被删" |

## 3 本机已证 / 本机不可证（这条区分是本卡判词的命门）

**本机已证**：

- `bash -n scripts/e2e/run_real_backend.sh` 通过；`pnpm exec tsc --noEmit` rc 0；mock e2e 全量 `31 passed / 11 skipped`。
- `ps` 能力探测在本机确实失败：`ps -p 1 -o args=` 取回空 ⇒ 新代码走"按 PID 直杀并说明原因"分支（`note: 本机 ps 不支持 -o args=…`），**这把文件头注里那句一直存在却没真发生的"退化"变成了事实**。
- 停路径两发（用 3290 这个 fake_llm 角色口，避开业务口 3200/3300；脚本 `Temp/s59/test67_stop.sh`）：
  - 一发（正常认领）：`stopped fake_llm pid=326` → `端口终检 fake_llm :3290 空闲；占用者读数：(本机没有 ss 也没有 lsof ⇒ 占用者取不到)`，`stop_rc=0`；
  - 二发（**牙齿**：端口上确有别人在听，pidfile 里是个不存在的 PID）：`already gone fake_llm pid=999999` → `❌ 本脚本起过的 fake_llm 还占着端口 3290（kill 后等满 6s 仍未释放，不静默放过）`，`stop_rc=1` ⇒ **宽限期没有把门洗软**，真泄漏照样红；
  - 收尾 `netstat` 复核 3290 已空闲（监听者用 Windows PID `taskkill` 清，MSYS PID 在这里不可靠——同族病史已记）。

**本机不可证，只能在 @ci 取（写清楚，不当已完成）**：

1. **新主判据本身**。本机既没有 `ss` 也没有 `lsof` ⇒ `port_owner_pids()` 恒空，端口属主这条路在本机走不到分支的"是属主 ⇒ 放行"那一支。二发证明的是"取不到属主时仍然红"，**不是**"属主判据生效"。
2. **① 的 real 分支**。本机无 docker / 无 PG / 无 Redis ⇒ 真栈起不来，`--project=real` 跑不了；`guest-landing-*.txt` 物证只能在 CI 的 artifact 里第一次出现。
3. ⇒ 本卡的终判是 `e2e-real` job 的两步同时 success（验收 ①②），加上 backend/`@win`/mock 三个计数不变（验收 ③④）。

## 4 为什么先做 67 而不是 60（D-V23-21 的实测依据）

`e2e-real` 的那一步命令是 `pnpm exec playwright test --project=real e2e/admin.spec.ts`（`.github/workflows/ci.yml` 现读），
**只跑 admin**；60 要跑的 `r19-chat-stream.spec.ts` 是同 job 的另一个 spec。所以两条既有红不挡 60 的**用例级**读数，
但会让 **job 级结论**恒红——60 之后任何一次红都得先回答"是不是那两条老的"。P-145 那一轮的代价正是这么付的：
一条被新分支遮蔽的旧文案，红了两次才看清。67 合起来不到 30 行，买到的是**红只可能来自新代码**这一件事。

## 5 归因自查（本卡有没有可能引入 mock 档回归）

`admin.spec.ts` 的 ① 在演示态**无条件执行**，所以 mock 档必测：`expectGuestLanding` 的 mock 分支与改前三条断言
逐项等价（同 `getByText("尚未登录或会话已过期")`、同 `toHaveURL(/\/admin$/)` 与 `/\/admin\/ops$/)` 语义——
后者由 `new RegExp(escape(path) + "$")` 生成）；实测 `31 passed / 11 skipped` 与基线同数，
`trunk.spec.ts:53`（同一句 AuthGate 文案）与 `auth-gate.spec.ts`（未登录访问 /admin 原地卡片）都在通过集里。
按卡面第 9 格：这两条任一红 ⇒ 立刻停手升级，实测没红。

---

## 6 一条比"两档差异"更麻烦的事实：冻结稿的 `unauthenticated` 与两档实现**三方两两不等**

现读 `docs/任务规划V0.12.0/contracts/ux_states.schema.json` 的 `x-core-views`（类型是 **list**，6 个视图，
带 `unauthenticated` 的恰好三处）：

| 视图 | 契约原文（逐字） | real 档实际 | mock 档实际 |
|---|---|---|---|
| `/spaces 列表 + /spaces/[id] 详情` | 「AuthGate 拦截 → 跳主平台 SSO，不得停留在空白页」 | 307 → `/` | 原地 AuthGate |
| `/chat 流式问答` | 「跳登录，保留提问草稿」 | 307 → `/`；草稿被清（`useSseAsk.ts:152`） | 原地 AuthGate |
| `/admin（管理端能力面）` | 「重定向登录」 | 307 → `/`（**不是** SSO） | 原地 AuthGate |

⇒ 契约说的"跳登录/跳主平台 SSO"在两档下都没发生：real 落的是**首页**（首页有登录入口，`app/page.tsx:69/77`），
mock 落的是**原地卡片**。而且「跳登录」在 CI 里根本不可达——`AIDEAN_ISSUER=http://127.0.0.1:9` 是关闭端口。
所以 67 **不按字面实现契约**，按 D-V23-15 的四条不变量实现，把落点差异登记为构建差异；
改这三处文字属冻结稿改动（D-V21-20 只有规划方能落笔）⇒ 登 **P-150**，本卡一字未动 `ux_states.schema.json`。

一条自查：上一段那个"三处"是**数出来的**，而且这次用视图键枚举而非子串计数——
因为 P-145 的教训就是"子串计数会数出不存在的东西"（同一文件里 `unauthenticated` 这个字面串其实出现 5 次：
3 处视图 + `State` 枚举 + 一处描述）。写"三处"的凭据是上表那三行，不是 `grep -c`。

---

## 7 只读复核批的处置（四条接受、一条部分接受、零驳回）

复核员看的是**提交后的字节**，不是我的转述。下面每条都标了"我原判/复核发现/对字节复算后的处置"。

| # | 复核发现 | 我对字节复算 | 处置 |
|---|---|---|---|
| 1 | §1/§2 与 commit message 里那句「端口终检**无条件**落一行属主读数」不成立 | 成立的那半是 `占用者读数` 两条路径都出现；不成立的那半是 `端口终检 … 空闲；占用者读数：` 这一整行——它在 `scripts/e2e/run_real_backend.sh:187`，位于 `while port_open` 循环**之后**，而红路在 `:175-177` 打完 `❌` + 缩进的 `占用者读数：` 就 `return 1`，永不触及 `:187`；且 `return 1` 会**中断整个角色循环**，排在后面的角色连终检都不做 | **接受并订正措辞**。判据② 仍然可满足（success 那一路确实会打出 `端口终检 … 占用者读数：(空)`，这一行是本批新加的），但"无条件"三个字是我把"读数两路都留"说成了"这一行每次都打" ⇒ 属**申报失真**，§1/§2 的原文不回改，以本节为准 |
| 2 | `s67_2` 是 `grep` 滤后的摘录（只有 18 条 ok），而卡面第 9 格拿 `trunk.spec.ts:53` 当升级锚 ⇒ 判据③"无误伤"从存证**复算不出来** | 复算成立：`s67_2` 全文只 3 条 trunk 行、`:53` 那条不在里面 | **接受并补证**：新增 `s67_3_mock_e2e_full_listing.txt`（未加滤网的 `--reporter=list` 原始 86 行）。现读 `Running 42 tests` / `ok`=31 / `-`=11 / `x`=0 / `e2e_rc=0`；`trunk.spec.ts:53` = `ok 34`（文件第 75 行），trunk 九条为 ok 34–42 全在通过集 |
| 3 | `s67_1:25` 那句"期望日志有『占用者读数：(空)』"与 §3 记录的实测读数（`(本机没有 ss 也没有 lsof ⇒ 占用者取不到)`）不符 | 复算成立：`${ownp:-(空)}` 的 `(空)` 只在**有** ss 或 lsof 且无人监听时才出现；本机两个都没有 ⇒ 走"取不到"文案 ⇒ 本机**永远不可能**打出 `(空)` | **接受**：不改 `s67_1` 的脚本抬头（那是当时的期望），在此标注口径——`(空)` 是 @ci（ubuntu 有 `ss`）才能取到的读数，本机那条只证明"终检留了行"，不证明留的是 `(空)` |
| 4 | `admin.spec.ts:133` 本批**新引入**一处产品文案字面量 `"使用主平台账号登录"`，与 D-V23-19（spec 不得硬编码产品文案）相对 | **有一半要还回去**：这个模式不是本批开创的——同一文件改前就已硬编码该串三处（`:65` 点登录、`:165`/`:167` 键盘可达），产品侧两处（`app/page.tsx:77`、`components/AuthGate.tsx:62`，另 `:71` 是正文句）。本批把该 spec 的实例数从 **3 抬到 4**，EVD 里此前对 `D-V23-19`/`硬编码` 零命中这一条复算成立 | **接受登记、驳回"新违反者"定性**：本卡不改（改成 import 要触第 7 格禁止面 `apps/web/components/**`），且 decision-log 里 D-V23-19 行末明文"不由 67 执行、归 69"⇒ 第 4 处随 69 的白名单/导入化一起收；P-146 已把"同一规则在我之前就失真"记在案，本行只是把计数从 3 更新到 4。mock 分支那句 `"尚未登录或会话已过期"` 是**旧断言原样搬运**、非本批新增 |
| 5 | kill 的分层里，**拒绝侧**被命令行特征覆盖了：`have_ps=1` 时（ubuntu 恰好如此）即便 `ownp` 非空且不含该 PID，代码仍进 cmdline 分支，碰巧匹配 `*"next-server"*` 就照杀；我的属主反证分支 `:129-132` 位于 `elif` ⇒ 在**唯一有属主证据的平台上不可达** | 复算成立（见上面的分支顺序）。复核员说"反证本批未交付"这半我要还一句：本机无 `ss`/`lsof` ⇒ `ownp` 恒空，二发（pid=999999）走的是 `kill` 失败后的 `already gone`，**属主反证在结构上只能在 @ci 取**，这一点 §3 已自陈 | **部分接受 ⇒ 登 P-151 交回，不在本卡第 2 轮改**：把它改严（"有属主证据且非属主 ⇒ 一律拒杀，不看命令行"）是字面合 D-V23-16 的，但风险真实——`next start` 的监听者若是被派生的子 PID，父 PID 就会被拒杀而端口仍被占 ⇒ `Stop stack` 红，这恰好是 67 要修的那个 bug 的反面。要改严需先量 CI 上 `ownp` 里到底有没有父 PID ⇒ 属设计取舍，归规划方；本卡先让第 1 轮读数落地 |

一处附带申报（复核员判"需规划方追认"）：卡面第 6 格字面列了 5 类去处，本批还写了 `docs/03_solution/decisions/decision-log.md`（+7 行，D-V23-15…21 代录）与
`docs/任务规划V0.23.0/07-执行过程记录.md`（+1 行）。两者都是治理面的既定惯例（裁决定期要入档、每卡要在 07 记一行），
但**字面确实越了第 6 格** ⇒ 在此明写，不当作"卡面本来就允许"混过去；台账行的越面同批申报。

复核员给的"另：卡面状态不得先写 ✅"我接受——本批提交时状态是 `🔄 在跑`，判据①② 没读 @ci 之前不动它。

---

## 8 第 1 轮 @ci 读数（head `4160b81`，run `40658539918`，原始存证 `s67_4_ci_round1_readings.txt`）

三条 workflow：CI `success`、CI-Windows `success`、Security `success`；CI 内 job：backend / frontend /
compose / compose-smoke / workflow-lint 全 success，**`e2e-real` = failure**（该 job `continue-on-error`
⇒ workflow 结论仍绿，所以三绿不等于判据过——判据要下钻到 job）。

### 判据① （E2E 步 success）— 第 1 轮**未过**，根因钉到字节

| 测试 | 读数 |
|---|---|
| ① 游客落点 | `✓ 1 [real] › e2e/admin.spec.ts:147:7`（**real 档首次跑通**——第 0 轮它从未执行过） |
| ②③④ | ✓ 2 / ✓ 3 / ✓ 4 |
| ⑤ 五屏切换 | `✘ 5 [real] › e2e/admin.spec.ts:236:9 (809ms)`，原文两行：`Error: strict mode violation: getByRole('button', { name: '登记' }) resolved to 4 elements:` |
| 汇总 | `1 skipped` + `3 passed (3.4s)` + `##[error]Process completed with exit code 1.` |

⑤ 是**被 ① 的成功第一次揭开面**：`describe.serial` 里 ① 前几轮恒红 ⇒ ⑤ 从来没真正执行过（P-145
同族——"老红遮着的东西，红第二次才看得清"）。逐字错文见 `s67_4:49`（错误块完整存证）。
处置 ⇒ 登 **P-152**：`admin.spec.ts:251` 的 `getByRole("button", { name: "登记" })` 在引擎密钥屏按
provider 行渲染、每行一枚 ⇒ 4 枚；改法属越面（spec 侧范围收窄），按用户批令执行（§9）。

### 判据② （Stop stack = success + 占用者读数行）— 第 1 轮**未过**，根因是本批新读数行自己触发了 `set -euo pipefail`

`s67_4:183-186` 的 Stop stack stdout 逐字：`stopped backend pid=4147` / `stopped frontend pid=4537`，
**两行之后零输出、退出 1**——终检循环一行都没打。机制：`scripts/e2e/run_real_backend.sh:24` 的
`set -euo pipefail` 下，`:186` 的 `ownp="$(port_owner "$port")"` 是个赋值——`port_owner` 末一条管道
`ss | grep | head` 在**端口空闲**时 grep 无命中 ⇒ 管道 rc=1（pipefail）⇒ 赋值 rc=1 ⇒ `set -e` 把整个
脚本就地中止。也就是说：**修掉的第 0 轮 bug（红路径永看不到读数行）被换成了"绿路径直接死"**——
读数行自己成了新故障点。本机当时不可能复现：无 `ss`/`lsof` ⇒ `port_owner` 恒走"取不到"分支（echo，
rc=0），只有 ubuntu（CI）才走得到 ss 分支。

### 三个计数不变（判据③④）

backend `2502 passed, 6 skipped, 4 deselected` + `Total coverage: 88.91%` + `skip 门禁：total_skipped=6 baseline=6 pg_unreachable=0`；
CI-Windows `1816 passed, 692 skipped` + `failed=0 total_skipped=692 baseline=692`；
frontend job success（mock e2e 同数 31/11）⇒ ③④ 无误伤。

### 两轮纪律说明

判据①② 各第 1 次 FAIL；第 2 轮已修（§9）。若第 2 轮再红同一判据 ⇒ 按 D-14 熔断登 P 交回。

---

## 9 第 2 轮：两处修 + 本机可证面

### 9.1 `run_real_backend.sh`（卡面第 6 格内）

修法是给读函数定契约：**`port_owner()` 永远成功、如实打印读到了什么**；失败语义归调用方的端口检查。
具体 = 末尾加 `return 0`（附注引 CI `4160b81` 的读数：两行 stopped 后静默 exit 1）：

```bash
port_owner() {
  if command -v ss >/dev/null 2>&1; then
    ss -ltnp 2>/dev/null | grep ":$1 " | head -2
  elif command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$1" -sTCP:LISTEN 2>/dev/null | tail -2
  else
    echo "(本机没有 ss 也没有 lsof ⇒ 占用者取不到)"
  fi
  return 0
}
```

**先红**（未改字节）：本机无 `ss` ⇒ 用假 `ss` 桩（`Temp/s59/stubbin/ss`：吐两行无关 LISTEN 后对目标端口
零输出、rc=0）前置 PATH 复现 ubuntu 形状——`--stop` 得 `stop_rc=1`、两行 stopped 后静默，与 CI 逐字同病。
**修后三发**（存证 `s67_5_sete_round2.txt`）：绿发 `stop_rc=0` + `端口终检 … 占用者读数：(空)`；
牙齿发（端口被别人占 + pidfile 是不存在 PID）`stop_rc=1` + `❌ 本脚本起过的 fake_llm 还占着端口 3290`
⇒ 宽限期没把门洗软。

### 9.2 `admin.spec.ts` ⑤ 两处定位器（**越面**，用户批令）

用户批令原文：**「授权甲，第 2 轮顺带改（推荐）」**——甲 = spec 侧范围收窄，不改产品语义；与 9.1 同批。

| 行 | 改前 | 改后 | 凭据 |
|---|---|---|---|
| `:251` | `getByRole("button", { name: "登记" })` → strict mode violation（4 枚） | `.first()`（断言改为"屏里登记入口可见"，不主张唯一） | CI `40658539918` 的 ✘ 5 原文 `resolved to 4 elements`；引擎密钥屏按 provider 行渲染、每行一枚登记钮 |
| `:255` | `getByText("分类清单")` → **潜伏同源雷**：`getByText` 是子串匹配，引擎标题 `分类清单`（`CollectionConfigPanel.tsx:177`）与保存钮 `保存分类清单`（`:269`）双命中 ⇒ 同型 strict violation | `{ exact: true }` | 修前对组件字节复核过才动手：`:177` `<p>分类清单</p>`、`:269` 按钮文本 `保存分类清单`。不改它就是把最后一轮赌在未验证的断言上 |

越面申报：第 6 格字面只列 `run_real_backend.sh` 与 `admin.spec.ts` 的 ①——② 的两行在 ⑤ 的测试体内，
属第 6 格未列的字节。按批令执行、在此明写，不当作"本来就允许"。

### 9.3 本地复验（改后字节）

`bash -n` 通过；`pnpm exec tsc --noEmit` rc 0；mock 档全量 `--reporter=list` 重跑
`31 passed / 11 skipped / e2e_rc=0`，42 条收集、`trunk.spec.ts:53` = `ok 34` 仍在通过集
（⑤ 在 mock 档本就 skipped，mock 计数不动是预期；实跑结果与预期一致）。

### 9.4 第 2 轮判据自陈（不预先声明完成）

判据①（E2E 步 success）与 ②（Stop stack = success + 日志可见 `占用者读数` 行）要等第 2 轮 @ci 才能判；
本机可证面到此为止——属主主判据的"是属主 ⇒ 放行"支、以及 ⑤ real 档全文，都只能在 CI 上第一次真跑。

---

## 10 第 2 轮 @ci 终判：② 首次通过、① 第 2 次红 ⇒ D-14 熔断交回（P-158）

head `3c4138d`，run：CI `40668413325`、CI-Windows `40668413716`、Security `40668413241`（原始读数
已存 `s67_6_ci_round2_readings.txt`；⑥ 逐字错文已存 `s67_7_test6_error.txt`）。
**编号注记**：本节初稿把登记号拟为 P-153，随后读台账发现 P-153/P-154 已被 V0.24.0 规划方
（`7c15264`，随 `a8f756b` 入库）占用 ⇒ 熔断登记顺延为 **P-158**，本节各处按 P-158 收口，不静默。

### 三条 workflow 全绿，计数判据 ③④ 全过

backend `2502 passed, 6 skipped, 4 deselected` + `Total coverage: 88.93%` + skip 门禁 6/6；
CI-Windows `1816 passed, 692 skipped` + `failed=0 total_skipped=692 baseline=692`；frontend success
（vitest `57 files / 449 passed`）；mock e2e 同数 31/11。

### 判据② — **通过**（本卡第一判据首次成立）

`Stop stack` 步 `conclusion=success`，stdout 逐字：

```
stopped backend pid=3991
stopped frontend pid=4314
端口终检 backend :3300 空闲；占用者读数：(空)
端口终检 frontend :3200 空闲；占用者读数：(空)
```

第 1 轮那个"两行 stopped 后零输出退出 1"的静默中止消失；`(空)` 这条 @ci 才能取的读数（§7 处置 3）
也就此取到——**`port_owner()` 契约修复在 ubuntu 的 ss 分支上真跑通**，且属主读数没有被删。

### 判据① — **第 2 次未过 ⇒ 熔断**

| 测试 | 第 2 轮读数 |
|---|---|
| ①-④ | ✓（① 397ms——real 档游客落点第二次跑通） |
| **⑤** | **✓ 711ms** ——第 1 轮的修复（`.first()` + `exact:true`）在 real 档成立 |
| **⑥** | **✘ 422ms** ——`admin.spec.ts:271` strict mode violation（P-145 → P-152 之后被 serial 遮蔽揭出的**第三层**；⑥ 自本卡开卡以来从未真跑过） |
| ⑦ | `did not run`（serial 同挡） |

⑥ 逐字错文：`bar.getByText(/告警|依赖未就绪|未知/)` resolved to **2 elements**——
① `<span data-tone="degraded">告警未启用</span>`；② `<p>依赖就绪，但告警探测器未启用（ALERTING_ENABLED=false）…</p>`。
注意红点不在 `:269` 首条断言（窄正则 `/告警未启用|…/` 单命中章），而在 `:271` 点击「重读」后的**宽正则**——
章与说明段都含「告警」二字 ⇒ 双命中。与 P-152 完全同族（getByText 正则/子串多匹配 ⇒ strict mode violation），
且 ⑥ 是**旧用例**（本卡第 6 格之外的字节，mock 档 skipped ⇒ 本机结构性复现不了）。

### 熔断判词

卡面第 9 格：「同一判据 2 轮未过 ⇒ 停，登 P 号，不动第 3 轮」。判据① 第 1 轮红在 ⑤、第 2 轮红在 ⑥——
**判据本身（E2E 步 success）两轮未过**，第 3 轮需规划方带裁决号授权。登 **P-158**；本卡状态按
D-V24-07（「仍红 ⇒ 登 P 号、标 ❌ 并交回」）标 **❌ 作废（有裁决行）**——本节初稿曾写 `⏸ 挂起`，
那是按旧词表自造的处置，与裁决行冲突，提交前订正为 ❌，在此如实注明。
（登记号 P-153/P-154 已被 V0.24.0 规划方占用 ⇒ 顺延 P-158；D-V23-03 词表的"Q 号"在本仓对应 P 号，如实注明不静默）。

若规划方授权第 3 轮，两条预审建议随 P-158 交付：⑥ 的修法候选甲=定位器收窄（同 ⑤ 的授权先例）/
乙=产品侧"章+说明段同信息双渲染"是否冗余（`components/**` 禁改面之外，需产品裁定）；
⑦（`:274-281`）没有 getByText 正则（`locator(".card.overflow-x-auto")` + evaluate），不在同族雷上，
但同样从未真跑过，授权轮开工前应照 P-152 的做法对组件字节预审，避免第四层单层剥。
