# STEP-59 交付读数（真后端 e2e 骨架档）

版 V0.22.0｜卡 `docs/任务规划V0.22.0/steps/STEP-59-真后端e2e骨架档.md`｜细则 `08-阶段A执行细则.md` §2
起算头 `c7c0a07`（STEP-61 交付头；08 §6 定的顺序是 61 → 59 → 60）｜本机侧口径 D-V22-01

逐字命令输出在同目录 `s59_1_local_readings.txt`，本文只做判读，不复制第二份数字。

## 1 原子步对照（08 §2 的 59.1～59.6 与 04 §1.1 的 1.1.0～1.1.5）

| 步 | 交付位置 | 判定 | 本机凭什么这么说 |
|---|---|---|---|
| 59.1 / 1.1.2 | `scripts/e2e/run_real_backend.sh`（新增，行数见 §6） | 已交付，实跑读数在 @ci | `bash -n` rc=0；`--stop` 在本机实跑过一条分支（rc=0，见 §7 第 7 项）。端口占用 rc=2、60s 探活 rc=4、seed 三条 rc=5、探针 rc=6、`/ready` 形 rc=8、前端 rc=7、终态自检 rc=9 都是**非零退出码 + 尾部日志**，不是 echo 警告 |
| 59.2 | `apps/web/e2e/real.setup.ts`（新增） | 已交付，实执行读数在 @ci | `tsc --noEmit` rc=0；解析正则按 `qa_seed_sessions.py:74` 的 print 模板做了形状核对（`s59_1` §④）。**没有**本机实跑：`--list` 不执行 globalSetup（实测两次 --list 都没有 `real.setup：…` 那行），而带 `-g` 的实跑会先按 config 起 webServer 抢 :3200，与共用工作树和端口铁律冲突 |
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
   **这条是本卡对 08 唯一的字面偏离，偏离方向由一条 rc=2 的红逼出来。**

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
  而**第一版本节把原因写成"只能由点按钮到达"是说过头的**，复核后改正：真后端档确实能画出那张卡
  （③ 已经用 `user.json` 证明了），卡点在**作用域粒度**——`test.use` 按 describe 生效、不能只换半段，
  整条换成 `user.json` 之后前半就画不出游客卡（`AuthGate.tsx:45-73` 只在 `status === "guest"` 渲染那个分支），
  "两卡都不溢出"会降级成"一卡不溢出"。⇒ 三选一：丢前半、丢后半、或逐段换会话的新代码（判据禁止那一类）。
  本卡选择把后半显式 skip 并按半段记数，并把"授权把 ④ 拆成两条用例（游客卡条挂 `undefined`、
  权限不足卡条挂 `user.json`）"作为可两全的出路写进 P-131 交给规划方——那要动用例结构，
  超出卡面第 6 格「仅开关与 storageState」，所以不由我自取。

处置与口径（这条最重要，别把 skip 读成"绕过"）：

- ② 整条、④ 后半段用 `test.skip(REAL_BACKEND_ENABLED, "<原因文本>")`，原因文本随 Playwright 的
  读数进日志，谁都能看出是"档不适用"而不是"用例不存在"；断言一条没删、没改、没放宽。
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
131   0  .github/workflows/ci.yml
  2   0  apps/web/.gitignore
 68  16  apps/web/e2e/admin.spec.ts
114   0  apps/web/e2e/real.setup.ts
 30   1  apps/web/playwright.config.ts
121   0  docs/06_validation/evidence/EVD-V22-59/s59_1_local_readings.txt
181   0  docs/06_validation/evidence/EVD-V22-59/s59_readings.md
  2   0  docs/任务规划V0.12.0/00-README.md
  1   1  docs/任务规划V0.22.0/04-剩余可执行大纲体系.md
  1   0  docs/任务规划V0.22.0/07-执行过程记录.md
  1   1  docs/任务规划V0.22.0/steps/STEP-59-真后端e2e骨架档.md
256   0  scripts/e2e/run_real_backend.sh
```

12 个文件（上面这 12 行）。其中代码与 CI 面全部落在卡面第 6 格内；第 7 格禁改面
（`apps/api/app/**`、`apps/web/lib/**`、`packages/contracts/**`、迁移、`mock-routes.ts`）零命中
（§3 的 0 计数读数）；台账两行与 07 一行是第 6 格没列、但队列纪律与 D-V22-01 要求必须动的笔，
连同 `admin.spec.ts` 与 `playwright.config.ts` 里两处比字面宽的动作，一并在 §8 申报。

- 这份 numstat 是**复核批改完之后**的暂存区复算值，不是第一版的值（第一版是
  `admin.spec.ts 58/16`、`playwright.config.ts 25/0`、`s59_1 97/0`、`run_real_backend.sh 183/0`）；
  增出来的 10 行 admin、5 行 config、24 行脚本、11 行 s59_1 都来自 §7 第 6～8 项那五处改正。
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
| `admin.spec.ts`：② 与 ④ 的 `test.skip`、③ 外面包一层 describe | 第 6 格写"仅开关与 storageState"。skip 算开关，包 describe 是让 storageState 生效所必需（`test.use` 只能按作用域生效），但两处都让 diff 面比"改一行开关"大 | 删 ②④ 的 skip 与 ③ 的包裹；代价是 real 档这两条按 08 原判据会红 |
| `playwright.config.ts` 的 `reporter` 条件展开 | 文件整体在允许面内，但 08 §2 59.3 没提 reporter；加它的原因是那条"上传 playwright-report"的判据否则是死的（§7 第 6 项） | 还原成只 `list`，并把 artifact 路径里的 `playwright-report/` 一起去掉，别留空判据 |
