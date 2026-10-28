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
