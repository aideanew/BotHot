# STEP-59 交付读数（真后端 e2e 骨架档）

版 V0.22.0｜卡 `docs/任务规划V0.22.0/steps/STEP-59-真后端e2e骨架档.md`｜细则 `08-阶段A执行细则.md` §2
起算头 `c7c0a07`（STEP-61 交付头；08 §6 定的顺序是 61 → 59 → 60）｜本机侧口径 D-V22-01

逐字命令输出在同目录 `s59_1_local_readings.txt`，本文只做判读，不复制第二份数字。

## 1 原子步对照（08 §2 的 59.1～59.6 与 04 §1.1 的 1.1.0～1.1.5）

| 步 | 交付位置 | 判定 | 本机凭什么这么说 |
|---|---|---|---|
| 59.1 / 1.1.2 | `scripts/e2e/run_real_backend.sh`（新增，行数见 §6） | 已交付，实跑读数在 @ci | `bash -n` rc=0；`--stop` 在本机实跑过一条分支（rc=0，见 §7 第 7 项）。端口占用 rc=2、60s 探活 rc=4、seed 三条 rc=5、探针 rc=6、`/ready` 形 rc=8、前端 rc=7、终态自检 rc=9 都是**非零退出码 + 尾部日志**，不是 echo 警告 |
| 59.2 | `apps/web/e2e/real.setup.ts`（新增） | 已交付，实执行读数在 @ci | `tsc --noEmit` rc=0；解析正则按 `qa_seed_sessions.py:74` 的 print 模板做了形状核对（`s59_1` §④）。**没有**本机实跑：直接探针实测 `--list` 不执行 globalSetup——给了一个合法 seed（三角色齐全）与 `E2E_AUTH_DIR` 之后跑 `--list`，两个变体（带/不带 `--project=real`）都 rc=0、都列出 11 条，而 `e2e/.auth` 与指定的 auth 目录**都没有被创建**（`ls` 报 No such file），所以不是"console 行被日志级别藏掉"。带 `-g` 的实跑会先按 config 起 webServer 抢 :3200，与共用工作树和端口铁律冲突 ⇒ 本机不取这份读数 |
| 59.3 / 1.1.3 | `apps/web/playwright.config.ts` | 已交付 | `E2E_REAL_BACKEND=1 … --list --project=real` 读 `Total: 11 tests in 2 files`；不带开关仍 `Total: 42 tests in 7 files`，与改前逐字同数 |
| 59.4 / 1.1.4 | `apps/web/e2e/admin.spec.ts` | 部分达成，缺口见 §4 | 同一批 --list 读数；①③④ 已换成游客／`user.json` 会话，⑤⑥⑦ 显式挂 admin 会话 |
| 59.5 / 1.1.4 | `.github/workflows/ci.yml`（新增 job `e2e-real`） | 已交付，job 是否出现在 run 列表在 @ci 验 | 仓库自带的 `js-yaml@4.3.2` 解析通过（本机无 actionlint、无 pyyaml，`s59_1` §③）；Actions 语义由 `workflow-lint` 那道 actionlint 1.7.12 判，不由我自称 |
| 59.6 / 1.1.5 | 本目录 | 本机段齐，@ci 段待回填 | §5 列明哪些还没有、由哪条命令取 |

## 2 先红两条（都是改前字节上取的真红）

1. `pnpm exec playwright test --list --project=real` 在改前读 **rc=1**：
   `Error: Project(s) "real" not found. Available projects: ""`。
   这一条证明"真后端档"今天确实不存在，不是我把一个已有能力重排了一遍。
2. 第二条红是实现过程自己冒出来的，不是我挑的：第一次 `pnpm exec tsc --noEmit` 读 **rc=2**，
   报 `'globalSetup' does not exist in type 'Project<...>'`。现读
   `playwright@1.63.0/types/test.d.ts`：`globalSetup` 声明在 `interface TestConfig` 区（1336 行），
   `interface Project`(760) 继承的 `TestProject`(111) 里没有这个键。
   ⇒ 08 §2 59.3 那句「`globalSetup` 仅在 `E2E_REAL_BACKEND=1` 时挂」如果按 project 级落笔，
   类型上过不去，就算强行写进去也要再赌一次"运行时认不认"。改成挂 config 顶层：真后端档只有
   一个 project，两种写法在同一判据下等价，而顶层写法少一层歧义。
   **这条是本卡对 08 的一处字面偏离**（不是唯一一处，全量清单见 §8 末段），偏离方向由一条 rc=2 的红逼出来。

## 3 零改动判据：判据本体有一条不可满足（登 P-132）

卡面验收③ 写 `git diff 12c87e9 -- apps/api/app` 为空，08 §2 59.6 写 `git diff 4ea83c4 -- apps/api/app` 为空。
两个锚点在本卡动手时都读到同一条非空结果：

```
apps/api/app/contracts/shapes.py | 15 ++++++++++-----
1 file changed, 10 insertions(+), 5 deletions(-)
```

归属读数：`git log --oneline 12c87e9..HEAD -- apps/api/app/contracts/shapes.py` 只有一条
`c7c0a07 feat(STEP-61 第 1 轮): MeWallet 契约封闭……`。也就是那 10/5 全部是 STEP-61 的交付本体
（08 §4 61.2 明写要改 `shapes.py`），而 08 §6 又把 61 排在 59 前面 ⇒ 这两处锚点在 59 这一棒**必然非空**。

本卡真实的零改动按"起算头"取，两条都是实测：

- `git diff c7c0a07 --numstat -- apps/api/app apps/web/lib packages/contracts apps/api/scripts` → 输出空；
- 提交前对暂存面复算同一条：`git diff --cached --name-only HEAD -- apps/api/app apps/web/lib packages/contracts apps/api/migrations apps/api/alembic.ini | wc -l` → **0**。

⇒ D-V22-02 的实质（产品代码零改动）成立；不成立的是判据的写法，已登 **P-132** 交回规划方定锚点或定通则。
STEP-60 验收④ 只写「`apps/api/app` 零改动」而没给比较锚点，同属需要一句话就能定清的歧义面，一并点名在该行里。

## 4 08 §2 59.4 的判据有两处在它自己给的约束下不可达（登 P-131）

判据原文两段（`08-阶段A执行细则.md` §2 表 59.4 行）：

> ①～④ 游客/非 admin 用例在 real project 下用 `storageState: undefined` 与 `user.json` 复跑（越权负例，零新增断言代码，只换会话）
> real 档 ⑤⑥⑦ 3 passed；①～④ 在 real 档也 passed

可照做的部分照做了：① 在 real 档挂 `storageState: undefined`（游客），③ 挂 `e2e/.auth/user.json`（非 admin 会话），
这两条就是"只换会话"，断言字节没动。⑤⑥⑦ 挂 admin 会话。

不可达的两处，都是同一机理：

- **②** 断言"回车之后落点是权限不足卡、URL 仍在 `/admin`"。那个落点只在演示态存在：
  `apps/web/lib/api/auth.ts:23-31` 的 `authLogin()` 在 mock 分支是
  `mockMarkLoggedIn()` + `window.location.reload()`，在真实分支是
  `window.location.href = "/api/v1/auth/login"`（后端 302 去主平台 authorize；本卡按 08 §2 59.1
  把 `AIDEAN_ISSUER` 指到关闭端口 `http://127.0.0.1:9`，正是为了"不触主平台"这条判据）。
  ⇒ 回车之后浏览器不会回到那张卡。要让它在真后端档真过，需要 02 §5 的方案 B（e2e 档起本地假主平台
  + 一条非 admin 的授权回调链），08 §2 没把它列进 59 的原子步，我没有自扩。
- **④** 前半段（游客卡 375px 不溢出）在 real 档可跑；后半段（权限不足卡）取不到，
  而**上一批（`git show a31dc42` 里本节）把原因写成"只能由点按钮到达"是说过头的**，复核后改正：
  真后端档确实能画出那张卡
  （③ 已经用 `user.json` 证明了），卡点在**作用域粒度**——`test.use` 按 describe 生效、不能只换半段，
  整条换成 `user.json` 之后前半就画不出游客卡（`AuthGate.tsx:45-73` 只在 `status === "guest"` 渲染那个分支），
  "两卡都不溢出"会降级成"一卡不溢出"。⇒ 三选一：丢前半、丢后半、或逐段换会话的新代码（判据禁止那一类）。
  本卡选择把后半在 real 档**不执行**（条件块 `if (!REAL_BACKEND_ENABLED)`）并按半段记数，
  另在 else 分支加一行 `console.log` 写明"real 档只证游客卡"——这条不是断言，是为了让报告里
  不至于出现"passed 却看不出少了一半"（第二批复核指出：条件块的 skip 在报告里零痕迹，
  我先前写"原因随读数进日志"对 ④ 不成立，现按代码现状改写）。
  同时把"授权把 ④ 拆成两条用例（游客卡条挂 `undefined`、权限不足卡条挂 `user.json`）"
  作为可两全的出路写进 P-131 交给规划方——那要动用例结构，
  超出卡面第 6 格「仅开关与 storageState」，所以不由我自取。

处置与口径（这条最重要，别把 skip 读成"绕过"）：

- ② 用 `test.skip(REAL_BACKEND_ENABLED, "<原因文本>")` ⇒ 报告里那条是 skipped 且带原因；
  ④ 的后半是条件块，唯一痕迹是上面那行 stdout。两种形态都在读数里说清，
  断言一条没删、没改、没放宽。
- 本卡对 real 档 admin.spec.ts 的读数口径写成 **执行 6／跳过 1（②）／失败 0**，
  且 **④ 按半段记**，不把没跑的那半算成已过。卡面第 3 格的目标是"⑤⑥⑦ 执行数 3、跳过 0、失败 0"，
  它不依赖 ②④，所以本卡交付本身成立。
- 冲突本体不由我改判据，登 **P-131** 交回规划方：要么改 59.4 的文字，要么先把方案 B 供给齐了另开卡再要求 ②。

## 5 本机不可证清单（不写成已完成）

| 待证项 | 由谁取 | 取法 |
|---|---|---|
| S59.0 探针（方案 A 还是 B） | @ci `e2e-real` | 启动器第⑥步：`/auth/me` 取不到 `is_admin:true` 就 rc=6 并打印"按 02 §5 走方案 B"，日志里必有一句结论 |
| seed 三行实生成、cookie 名实取 | @ci | 启动器第⑤步要求 `grep -c '^session '` 恰为 3，否则 rc=5；`real.setup` 缺任一角色则抛错 |
| ⑤⑥⑦ 3 passed、①③④ 在 real 档读数 | @ci | `pnpm exec playwright test --project=real e2e/admin.spec.ts` 的 list reporter 末行 |
| job 是否出现、时长、结论 | @ci | run 列表与 job 时长；`concurrency` 组连推时会有 cancelled，读 attempt 与 conclusion 而不是只看 status |
| 截图产物 | @ci artifact | real project 开 `screenshot: "on"`，job 的 artifact 步是 `if: always()` |
| 四屏截图（04 §1.1.5 原句） | — | 08 §2 59.6 未列这一项，按 08 首行"冲突以本文为准"处理；`screenshot: "on"` 给的是**每条用例一张终态帧**，不是一屏一张，所以我**不**把它写成"1.1.5 已满足" |

## 6 本卡字节面（暂存区实测 numstat）

```
按批次拆开，每批都是当时的暂存区复算值（三段合起来才是本卡字节面，别把中间任何一段当终态）：

| 文件 | 第 1 段 `c7c0a07→a31dc42` | 第 2、3 段（本提交）逐文件终值 | 说明 |
|---|---|---|---|
| `.github/workflows/ci.yml` | 131 / 0 | 见本节末"本卡累计"表 | 第 2、3 段只改 `if:` 与加自检步 |
| `apps/web/e2e/admin.spec.ts` | 68 / 16 | 同上 | 第 1 段是 58/16，复核批补到 68/16 |
| `apps/web/playwright.config.ts` | 30 / 1 | 同上 | 第一版是 25/0 |
| `scripts/e2e/run_real_backend.sh` | 256 / 0 | 同上 | 第一版 183 行 |
| `EVD-V22-59/s59_1_local_readings.txt` | 121 / 0 | 同上 | 第一版 97 行 |

上一批这里写过一句"增出来的 10 行 admin、5 行 config、**24 行脚本、11 行 s59_1**"——那两个数字是
错位誊抄：按同一段自己的数逐个减，脚本是 `256−183 = 73`、s59_1 是 `121−97 = 24`；
另外我把改正说成"那五处"，按 §7 第 6 项 + 第 7 项①②③④ + 第 8 项数下来是**六处**。
两处都是我的算术错，不是口径不同，所以连同这段一起留在本节里当反例。

**本卡累计（`git diff --numstat c7c0a07 <本提交>`）**：

```
145   0  .github/workflows/ci.yml
  2   0  apps/web/.gitignore
 74  16  apps/web/e2e/admin.spec.ts
120   0  apps/web/e2e/real.setup.ts
 30   1  apps/web/playwright.config.ts
187   0  docs/06_validation/evidence/EVD-V22-59/s59_1_local_readings.txt
248   0  docs/06_validation/evidence/EVD-V22-59/s59_readings.md
  3   0  docs/任务规划V0.12.0/00-README.md
  1   1  docs/任务规划V0.22.0/04-剩余可执行大纲体系.md
  3   0  docs/任务规划V0.22.0/07-执行过程记录.md
  1   1  docs/任务规划V0.22.0/steps/STEP-59-真后端e2e骨架档.md
317   0  scripts/e2e/run_real_backend.sh
```

12 个文件（`git diff --name-only c7c0a07 | wc -l` 同值）。代码与 CI 面全部落在卡面第 6 格内；第 7 格禁改面
（`apps/api/app/**`、`apps/web/lib/**`、`packages/contracts/**`、迁移、`mock-routes.ts`）零命中
（§3 的 0 计数读数）；台账两行与 07 一行是第 6 格没列、但队列纪律与 D-V22-01 要求必须动的笔，
连同 `admin.spec.ts` 与 `playwright.config.ts` 里两处比字面宽的动作，一并在 §8 申报。

- 这份 numstat 是**复核批改完之后**的暂存区复算值，不是第一版的值。与 `a31dc42` 里那份（我引的第一版）
  的差是逐个减出来的，不是估的：`admin.spec.ts` 58→68（+10）、`playwright.config.ts` 25→30（+5）、
  `run_real_backend.sh` 183→256（**+73**）、`s59_1_local_readings.txt` 97→121（**+24**）。
  ⇒ 上一批这里写的是"24 行脚本、11 行 s59_1"，两处都错（脚本的 +24 其实是 s59_1 的差，s59_1 的 +11
  是 config 与 admin 的差被错位誊抄）；第三批又在这四个数上继续变，所以下面这行只说方向不说值：
  **本表就是 `git show --numstat HEAD` 的现算值，任何引用它的散文都必须重新减一遍。**
- 上一批还说改动是"那五处"：按 §7 第 6 项（reporter）+ 第 7 项①②③④（四处）+ 第 8 项（版本钉住说明）
  实际是**六处**，第五处与第七处之间我数错了一次。
- 本文件自己那一行的数字是行数而非字节数，改它只动数字、不动行数 ⇒ 这条读数可复核、不会漂移。
- `admin.spec.ts` 的 68/16 里含一次结构性缩进：③ 为了按 describe 作用域换 `user.json`
  会话被单独包了一层 `test.describe`（Playwright 的 `test.use` 只能按 describe 生效，不能逐条用例），
  断言文本逐字未改。
- `playwright.config.ts` 的 30/1 里那一行删除就是 `reporter: [["list"]]` 换成条件展开那一处。
- `docs/任务规划V0.12.0/00-README.md` 的 2/0 是两行新登记（P-131、P-132），只追加、未回改既有行。
- 行尾：`.gitattributes` 钉 `* text=auto eol=lf`，`git add` 时 git 自己报了 5 个
  "CRLF will be replaced by LF"（工作树里这些文档是历史检出留下的 CRLF）。
  入库 blob 全 LF，与改前该文件的存储形态一致 ⇒ 上面 04 的 1/1、07 的 1/0、卡面的 1/1 才可能这么小。

## 7 自查：这份证据可能把什么写成假的

1. "已交付"只指字节进了这一批，不指 e2e 跑通——§5 表把跑通那一半整个挂在 @ci，没有一处写成已过。
2. §1 表里 59.5 那格的"解析通过"只证 YAML 语法，不证 Actions 语义；我把两个判据分开写，
   防止下一个读者把 js-yaml 绿当成 job 可用。
3. §3 的"输出空"是真跑出来的空，不是推断出来的空——我先跑过两个卡面锚点、看到 10/5，
   才去查归属；如果我只跑起算头那一条，就会漏掉整条 P-132。
4. §4 的"不可达"是读了 `lib/api/auth.ts` 与 `AuthGate.tsx` 之后的判断，不是"我做不到所以跳过"。
   **但本节第一版把 ④ 的成因写错过**（写成"只能由点按钮到达"，实际卡点是 `test.use` 的作用域粒度），
   是只读复核批读出来的，现已在原位改正并在 P-131 里按改正后的口径写。留这句是因为：
   一处说错的成因会把规划方引向错的出路（以为要造方案 B 才能救 ④，其实拆成两条用例就够了）。
5. 42 与 CI 里 `31 passed` 的关系（42 条中 11 条在演示态 skip）写在 `s59_1` §①，
   免得下一个读者以为我把 mock 档的基数改大了。
6. 一处**曾经写成死路**的判据已改正：`e2e-real` job 最初把 `playwright-report/` 列进 artifact 路径，
   而 config 只有 `reporter: [["list"]]` ⇒ 那个目录在任何一次跑里都不存在，上传步会"绿着上传空目录"，
   08 §2 59.5 的"失败时上传 playwright-report"看着满足、其实是空的。现改成真后端档
   `reporter: [["list"], ["html", { open: "never" }]]`（演示档仍只有 list，CI 的 mock e2e 步骤按那份输出取数）。
7. 复核批另读出的四处也一并改掉，记在这里免得下一条卡重犯：
   ①`--stop` 只 kill 得到包装进程（`pnpm exec next start` 的真监听者是子进程），前端改成
   `exec node ./node_modules/next/dist/bin/next start -p 3200`，pidfile 里的 PID 就是服务本身，另加
   `pgrep`/`pkill` 特征兜底与端口终检（本机 git-bash 无 pgrep/pkill，实测 `--stop` 走的是"三端口空闲"
   那条分支并 rc=0；CI 的 ubuntu runner 两个都有）；②pidfile 改**增量**落盘 + 非零退出即拆
   （旧写法只在成功路径落盘，失败后 uvicorn 留在端口上、下一次只看到 rc=2"端口被占"）；
   ③`/ready` 的 HTTP 码原本"取了、打印了、没有任何退出码依赖它"，现按 {200,503} 判定，
   不合法用**独立的 rc=8**，好让它不会被读成"S59.0 红 ⇒ 走方案 B"（那是 rc=6）；
   ④Windows 上 seed 若是 CRLF，`$(...)` 只剥尾换行不剥尾 CR，第⑥步取到的 `COOKIE_VALUE` 会带 `\r`
   而使 curl 请求头畸形 ⇒ 解析前先 `tr -d '\r'`（`real.setup.ts` 侧本来就按 `/\r?\n/`，两份解析器原本不对称）。
8. `storageState: undefined` 这条写法按版本钉住：复核在 playwright 1.63 源码里核到它确实生效
   （scope 构建时照登记这个键，组装 contextOptions 时见 `undefined` 就不带 storageState），
   但它不是文档化惯用法 ⇒ 升级 Playwright 时先看 real 档 ① 是否仍以游客态跑，再采信这份读数。

## 8 越界申报（本卡改到、但不在卡面第 6 格逐字列出的面）

卡面第 6 格给的是：`scripts/e2e/**`、`apps/web/playwright.config.ts`、`apps/web/e2e/admin.spec.ts`
（仅开关与 storageState）、`apps/web/e2e/real.setup.ts`、`apps/web/.gitignore`（仅加 `e2e/.auth/`）、
`.github/workflows/ci.yml`、`docs/06_validation/evidence/EVD-V22-59/**`、本卡与卡表。
以下几处超出这份字面，申报而不是解释成允许：

| 越界项 | 为什么还是做了 | 不接受时的回滚单位 |
|---|---|---|
| `docs/任务规划V0.12.0/00-README.md` 追加 P-131、P-132 | 台账只追加纪律要求"判据不可满足 / 同判据 2 次 FAIL ⇒ 登 P 号交回"，那张表不在任何一张卡的允许面里，是所有卡共有的一道笔 | 删两行即可，代码面不受影响 |
| `docs/任务规划V0.22.0/07-执行过程记录.md` 追加一行 | D-V22-01 明写"卡面勾选、卡表、执行记录与交付放**同一个提交**" ⇒ 07 是这一批必须动的文件 | 删该行 |
| `admin.spec.ts`：② 的 `test.skip`、④ 后半的**条件块**（不是 skip）、③ 外面包一层 describe | 第 6 格写"仅开关与 storageState"。skip 算开关，包 describe 是让 storageState 生效所必需（`test.use` 只能按作用域生效），但两处都让 diff 面比"改一行开关"大。**④ 的形态按字节更正**：它是 `if (!REAL_BACKEND_ENABLED){…}`，real 档走到 else 打一行 stdout，用例仍计 **passed**、不产生 skip 记录——本文件上一批、`04` 卡表那一行与台账 P-131 都把它写成"显式 skip 带原因"，与代码不符，已由 P-133 更正（只追加纪律下不回改已入库行） | 删 ②④ 的两处分支与 ③ 的包裹；代价是 real 档这两条按 08 原判据会红 |
| `playwright.config.ts` 的 `reporter` 条件展开 | 文件整体在允许面内，但 08 §2 59.3 没提 reporter；加它的原因是那条"上传 playwright-report"的判据否则是死的（§7 第 6 项） | 还原成只 `list`，并把 artifact 路径里的 `playwright-report/` 一起去掉，别留空判据 |

### 8.1 本卡对 08 §2 的字面偏离——完整三条（上一批说"唯一一条"是过度陈述）

| 偏离 | 08 原文 | 本卡字节 | 依据 |
|---|---|---|---|
| globalSetup 挂 config 顶层而非 project | 59.3「`globalSetup` 仅在 `E2E_REAL_BACKEND=1` 时挂」（写在 project 语境里） | config 顶层条件展开 | `Project` 类型无此键，tsc rc=2 实测 |
| 端口预检只查"这一棒要用的"那几个 | 59.1 ①「检查 3200/3290/3300 未被占用」 | `--no-frontend` 不查 3200；不带 `--with-fake-llm` 不查 3290 | D-V4-02 禁的是换口，不是少查；恒查三个会让 59 阶段用不到 :3290 的每一棒都被一个 STEP-60 才交付的端口挡死 |
| artifact 步 `if: always()`（成功也上传） | 59.5「**失败时**上传 playwright-report 与 uvicorn 日志」 | 无条件上传 + 新增 `Reporter 自检` 步 | 04 §1.1.5 要"四屏截图"，只在失败时上传就拿不到绿跑截图 ⇒ 04 与 08 冲突时取并集而不是各半 |

另：`admin.spec.ts:186` 那句"改名…登记为 nit 交回规划方"上一批是**无出处的**（P-131/P-132 里都没有这条），
现已由 P-133 补登记，那句话才有指涉对象。

## 9 第二批复核（只读）与它的对错

第一批交回后我又发了一轮只读复核（同一个 reviewer 类型、独立会话）。它报了三条 BLOCKER 与一批 NIT，
其中**两条我照改、一条它自己读错了**。逐条按"复现还是反驳"记，反驳也要留下复现命令，
否则下一棒只能信一个没有出处的结论。

| 复核结论 | 我的处置 | 复现/反驳的读数 |
|---|---|---|
| `--no-frontend` 仍挡已有后端（第③步无条件起 uvicorn，端口预检含 3300），而我在提示与提交说明里写成"真的能复用已有栈" | 承认，**代码语义不动**（复用整栈不是本卡需求），把两处文字改成实话：`--no-frontend` 只是不起前端，3300 仍要空闲；要复用整套就别跑本脚本、直接备 `E2E_SEED_FILE` | `bash scripts/e2e/run_real_backend.sh --no-frontend` 在 3300 被占时仍 rc=2（读代码即得：端口检查列表恒含 3300） |
| 种子脚本非零退出时 rc=5 那条分支不可达（python 的 rc 先把脚本打死，stdout 也没落盘） | 加 `|| SEED_RC=$?` 捕获、判定改 `n_session != 3 或 SEED_RC != 0` ⇒ rc=5 真能带上 traceback 到达 | 同族惯用法单测：`set -euo pipefail` 下 `(python -c "import sys; sys.exit(1)") > f 2>&1 || RC=$?` 读到 `captured_rc=1` 且继续执行到下一行（`s59_1` §⑥） |
| html reporter 在本 pnpm 布局里解析不到 `@playwright/test`，真后端档"任何一条用例之前"就会崩 | **反驳，未照改**。它引的 `playwright/lib/reporters/html.js` 在这个安装里根本不存在（`ls node_modules/.pnpm/playwright@1.63.0/node_modules/playwright/lib/` 只有 agents/cli/common/…，没有 reporters 目录）；它引的 `package.json` 实为 `name=playwright version=1.63.0`（不是 playwright-core） | 三条实测：`--list --project=real` 现在 rc=0 且没有 "Cannot find module"；`--reporter=html --list` 之后 `playwright-report/` 目录出现（10:04:56）；从 reporter 所在目录 `require.resolve('@playwright/test/package.json', {paths:[…]})` 成功（pnpm 有 `.pnpm/node_modules` 这层解析兜底） |
| 那条"上传 playwright-report"的判据即使加了 reporter 也可能是空的 | 不赌：**加一步会红的自检**（`Reporter 自检`：目录不存在就 exit 1），把空判据改成可失败判据 | ci.yml 新增步，job 现 12 步（js-yaml 复算 `steps=12`） |
| `pkill -f "…--port 3300"` 会命中别人的后端；rc=2/3 的 trap 更会 | 承认。特征兜底只留两条**带本 checkout 绝对路径**的（next 的 bin、fake_llm.py），uvicorn 只按 pidfile 里的真 PID 杀（exec 之后 PID 就是它本身）；端口终检改成"只对本脚本起过的角色判" | 本机 `command -v pgrep` 为空 ⇒ 新加的 `note:` 分支实测打到 stdout（`s59_1` §⑥ 第二段） |
| `AIDEAN_PUBLIC_URL` 的注释说它是 issuer 的缺省回退 | 承认，注释改成实话：它只进登录路由的 authorize 拼装（`app/api/v1/auth.py:63`，字段默认空串 `config.py:31`），第⑥步两个探针都不走登录路由 | 现读该行代码 |
| seed 行解析没管 CRLF（`$(...)` 只剥尾换行不剥尾 `\r`），而 real.setup.ts 侧本来按 `/\r?\n/` ——两份解析器不对称 | 承认。第⑤步之后统一 `tr -d '\r'` 到 `$RUN_DIR/seed.lf.txt`，计数与探针都读这份 LF 副本 | 见 §7 第 7 项④ |
| `BACKEND_ORIGIN` 没钉，rewrite 靠 next.config 的缺省值 | 承认。启动器显式 `export BACKEND_ORIGIN=${BACKEND_ORIGIN:-http://127.0.0.1:3300}`，与端口预检的 3300 同源 | `next.config.mjs:9-16` 现读（引用也从 9-15 改成 9-16） |
| `expires:-1` 的理由写得含糊 | 承认，改成"Playwright 的负数到期只接受 -1 + 这一档的会话不需要跨 run 存活"，并说明镜像 `max_age` 的是后端那份 cookie、不是注入的这份 | `real.setup.ts` 注释 |
| "`--list` 不执行 globalSetup" 只是从"没打印 console.log"推出来的 | 承认推理弱，**改法**：给一个合法 seed 与显式 `E2E_AUTH_DIR`，跑带/不带 `--project` 两种 `--list`，两条都 rc=0 且**目录没被创建**（`ls` 报 No such file）⇒ 结论不变，但现在是直接探针而不是日志推断（`s59_1` §⑦） |
| 我说"12 个文件（上面这 12 行）" | 承认：表是 13 行、文件是 12 个；改成"共 12 个文件；表里 13 行是因为…"并按实测重算 §6 | `git diff --cached --name-only \| wc -l` |
| 07 行与 §7 里"本行第一版/本节第一版"没有可指字节 | 部分承认：本文件（`s59_readings.md`）的上一版**是入库字节**，所以 §4 现在引 `git show a31dc42`；07 行那条错文确实从没进过提交，所以 07 行改成"入库前草稿"而不是"第一版" | `git log --oneline -- docs/任务规划V0.22.0/07-执行过程记录.md` |

同一批还落了两处口径：`guard-ci-secret-mask` 那句"job 级口径"是我把 compose-smoke 的注释读成了门的粒度
（门的实现在 `scripts/guards.py:186-187`，按 job 汇总），新步只是沿用同一写法、没有新增保证；
以及复核提的"artifact 里 `${{ runner.temp }}` 在默认 shell 下不可解析"这条与第一批复核的
"`runner.temp` 在 step 级合法"直接冲突——按 GitHub 的上下文规则取后者（`with:` 是步骤级，允许 `runner`），
并且这一步本来就 `if: always()` + `if-no-files-found: warn`，不依赖它判定成功。
