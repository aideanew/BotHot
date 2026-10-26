# EVD-V21-55 契约链补洞与本机门复算（执行助手）

平台 @win（Windows 10 x64，便携 PG16.15@5547 的 `bothot_test`，跨会话持久库）。开工 head `e4a9a67`
（STEP-54 收口批；其交付头 `4245847` 三绿 CI 40272848476 / CI-Windows 40272848421 / Security 40272848410，
均 attempt 1）。时间 2026-10-26（Asia/Shanghai）。
卡面基线写 `92af50a`，开工现读已是 `e4a9a67`——差的是 54 的交付与收口两批，本卡允许面
（`scripts/check_module_coverage.py`、`apps/api/tests/test_module_coverage_gate.py`、两个前端文件、新前端测试）
在其中零改动：`git log --oneline 92af50a..HEAD -- scripts/check_module_coverage.py apps/web/lib/api/spaces.ts` 零命中。

本卡交付面五件（`git status` 逐条对得上，无越界）：

| 文件 | 性质 |
|---|---|
| `apps/web/tests/s55-mock-runtime-shape.spec.ts` | 新增（S55.1 运行时形状门） |
| `scripts/check_module_coverage.py` | 改（S55.2 `_norm`/`_match` 归一 + 末段 stdout 编码钉） |
| `apps/api/tests/test_module_coverage_gate.py` | 改（S55.2 常驻用例 11 → 16） |
| `apps/web/lib/api/spaces.ts` | 改（S55.3 注释） |
| `apps/web/lib/api/types.ts` | 改（S55.3 30101 文案旁的说明，文案本体一字未动） |

## S55.1 运行时形状门（P-124 / D-V21-12）

新 `apps/web/tests/s55-mock-runtime-shape.spec.ts`。做法与卡面一致：**不写任何键清单**，
从 `packages/contracts/schemas/{shapes,engine}.schema.json` 现读 `$defs` 做递归核对；
样例走**真实分发器**（`matchMockRoute` → `buildMockContext` → `route.handle`），
所以"那句 satisfies 还在不在"不再是判据的前提。

### 规模（原文 `s55_1_checker_sizes.txt`，按大括号配平数出来）

| 件 | 行数 | 卡面约束 |
|---|---|---|
| `checkShape`（递归核对器） | **78** | ≤80 的纯函数 ✅（两轮审查之间加了两族判据，靠合成两行写法换回来的，见下） |
| `jsonType` | 5 | 辅助（类型名翻译），无 IO |
| `loadDefs` | 15 | 装载两份 schema 并合并；同名 def 直接抛，不猜 |
| `auditDefs` | 33 | 契约写法体检（装载期全树判，见下） |
| `own` | 1 | 只认自己的键 |
| 整个测试文件 | 439 | 含 22 条路由的输入面 `ROUTE_OVERRIDES` 与两条用例 |

### 它判什么

结构层：`type: object/array/string/integer/number/boolean/null`、`properties`、`required`、
`additionalProperties`（只有显式 `false` 才禁多键——`MeWallet` 是 `true`，那是 P-121 登记的唯一开放对象，
多键放过是**契约说的**）、`items`、`$ref`（只认 `#/$defs/<名>`）、`anyOf`（可空位）、`enum`。
取值层：`minimum`/`maximum`/`exclusiveMinimum`/`exclusiveMaximum`/`minLength`/`maxLength`——
这些是契约真声明的约束（现测 32/0/0/1/3/4 处，见 `s55_1_checker_blindspot_audit.txt`），
不是注解；`limit≥1`、`qualityScore 0..100`、`count≥0`、`engine` 长 1..32 都在里面。
真正只当注解忽略的键单列成 `ANNOTATION_ONLY`（`description`/`title`/`default`/`examples`/`deprecated`/
`format`/`pattern`/`$id`/`$schema`/`$defs`/`x-*`）——**这一分为二很重要**：范围族如果还留在注解名单里，
`$ref` + `minimum` 这种写法会被体检当成"只是注解的同级键"放过（第二轮审查点名的洞，现测 0 处，
但放过的那天就是静默丢约束）。`pattern`/`format` 现测各 0 处，所以"忽略"今天不放过任何已声明的约束。
分发层三条钉：①匹配到的路由必须就是表里这条（`normalizeRouteKey` 逐条比）；②`paramNames` 声明的个数
必须等于 pattern 里**真实捕获组**的个数（旧写法只在 `paramNames` 非零时比数量，删掉它这一判据整条跳过，
handler 读 `?? ""` 走兜底分支、响应照样合契约）；③分页壳带 query 那一发的 `limit`/`offset` 必须回显请求值
（默认那 22 发一律传空 search，"回显"这条腿以前从没被走过）。

**认不出的构造一律抛错**，与生成器同纪律——一门不知道自己在判什么的门比没有门更坏。
`checkShape` 在被走到的那一层抛；`auditDefs` 在**装载时对整棵 def 树**抛六类：
对象缺 `additionalProperties`、数组缺 `items` 或写成 tuple、`$ref` 与同级结构键并存、
`anyOf` 与同级结构键并存、`required` 的键不在 `properties`（那会把**正确**的样例判红）、
属性名撞 `Object.prototype`、以及 `KNOWN` 之外的任何关键字（`oneOf`/`const`/`patternProperties`/`minItems`…）。
为什么必须往装载期搬：`checkShape` 只判被样例走到的层，可选键没填 ⇒ 那下面的写法永远不会被 visit。
这七条拒绝路径各有自己的 `toThrow` 用例（自检那条 `it` 现在共七份证明），且现测全部为 0 处
（`s55_1_checker_blindspot_audit.txt` ①⑧）⇒ 今天不改变任何判定，只是把"未来某天静默失效"关死。

跑出来的事实：**24 次分发（22 条路由 + 抽取低质支 + 带 query 的分页那一发）全部与契约同形，零 errors**，
加边界判据与分发层三条钉之前之后都是零。
⇒ 没有触发卡面第 14 格那条（样例与契约不同形就要登记 P 号交回）；STEP-52 铺的 `satisfies`
在运行时这一层也对得上，这是独立于 tsc 的第二份证据。

三条判据里的"空数组跳过元素层"记账是现测得的三条，且两两有理由：`history.items`（演示态没有真实历史）、
`ExtractedArticleView.qualityReasons`（高质量分支无理由可列）、低质分支的 `images`（短文无配图）。
关键是**抽取的两个数组位置在两支合起来后被真核对过**：`images` 在高质量支非空、`qualityReasons` 在低质支非空
——只跑默认支就会有一半元素形状没人看。写死成清单的意义：将来任何一条样例悄悄退化成空数组，
这条判据会红并要求写清为什么。

### 先红与反证（最终代码上重跑，原文 `s55_probe_readings.md` + 十三份 `s55p2_*.txt`）

卡面第 7 格①的两半，加上本轮新写的每一条判据自己的红（A–H 八条，逐条驱动原文与 sha 复核都在那份里）：

| 探针 | 覆盖面门 s52 | tsc | 新形状门 | 要点 |
|---|---|---|---|---|
| A 摘 `satisfies` **并**多一个契约外键 | **0（看不见）** | **0（看不见）** | **1（抓住）** | 这就是 P-124 的正面闭合：同一份漂移，旧两道门全绿、新这道红 |
| B 只删契约必填键（`satisfies` 留着） | — | 2（TS1360） | 1 | 类型层与运行时层各判得住 |
| C 页宽默认 50→0（越 `minimum:1`） | — | 未跑（`limit: number` 结构性判不住） | **1** | 三个分页壳同时红——边界判据在真分发器上是活的 |
| D 详情路由的样例路径指向列表路由 | — | — | **1** | `分发器匹配到的是另一条路由（表里 "GET /api/v1/spaces/{seg}"，实际 "GET /api/v1/spaces"）` |
| E 输入表留一个旧路由名 | — | — | **1** | `ROUTE_OVERRIDES 里有对照表没有的键` |
| F 摘掉 stdout 编码钉（属 S55.2） | — | — | pytest 1 + 原样命令 1 | 判绿末行 `✅` 与判红末行 `❌` 两侧的崩都有裸读数 |
| G 删掉一条路由的 `paramNames` | — | 0（可选字段，类型层看不见） | **1** | `pattern 捕 1 段，paramNames 只声明 0 个`——旧写法整条跳过的那一刀 |
| H 分页 handler 的 `limit` 写成常量 50 | — | 0 | **1** | `分页 limit 没回显请求值（query 里是 7，响应给的是 50）`；**H 第一次跑是 rc=0**，因为我锚到了另一个分页壳——那次不算证据，写在这里是因为"探针打错位置"给的绿比红更危险 |

A/B 两行第一轮（14:24–14:29）也在旧一版核对器上跑过，那份驱动原文与当时的字节 sha 另存
`s55_probe_readings_round1.md`（+ `s55_probe_*.txt` 九份）；闭合证据以 A–H 批为准。
每次探针都按 sha256 证明字节还原（八行 `RESTORED … -> True` + 末尾 `sha_all_equal=True`），
`git status` 末态不含 `mock-routes.ts` ⇒ 本卡对样例取值零改动（卡面第 11 格）。

`dispatched` 与 `emptyArrays` 都是硬断言（条数 24、跳过清单三条有序），不是为了好看：
少分发一条、或多一处静默跳过，都会在这一条上红。

## S55.2 `_match` 键形归一 + 这条门在 @win 的第二条复算不了的因（P-125 / D-V21-13）

### 其一：键形

改 `scripts/check_module_coverage.py`：新增 `_norm`（反斜杠→斜杠、去前导 `./` 与前导 `/`），
`_match` 改成两侧都归一后要求"全等"或"以 `/`+键结尾"。旧实现把 needle 拼成带前导斜杠的后缀，
而本机 `coverage.json` 的键是 `app\__init__.py` 这种反斜杠相对形 ⇒ 8 条阈值键全部"命中 0 个"。

改前/改后逐例对照（同一份真机 `coverage.json`，原文 `s55_2_old_vs_new_match.txt`）：

| 输入形状 | 改前命中 | 改后命中 |
|---|---|---|
| @win 反斜杠相对键（本机 coverage.json 的真形） | 0 | 1 |
| @linux 正斜杠相对键（CI 的真形，见下"键形为什么两侧不同"） | 1 | 1 |
| 手造的深度绝对形（负例，**不是 CI 实测**：/home/runner/.../app/services/kb.py） | 1 | 1 |
| 手造的 `./` 前缀形（负例） | 1 | 1 |
| 真该报的"多命中"（`app/services/kb.py` + `other/app/services/kb.py`） | **1（静默只判其中一个）** | **2（调用方据此 NOT-PASS）** |
| 不该命中的近似名（`xkb.py` / `kb_more.py` / 别的目录） | 0 | 0 |

**键形为什么两侧不同（P-125 的"待确认"就地转成已确认）**：CI 那一步打印的文件列就是它看到的键形——
`app/providers/article_sources/dajiala.py` 这种**相对形 + 正斜杠**，与阈值表逐字相同，所以旧 `_match`
的第一条快路径（`key in files`）在 CI 一直命中；本机同一份产物是 `app\services\kb.py`（coverage.py 的
相对键用 `os.sep`）。⇒ 差异只在**分隔符**，不在"绝对 vs 相对"或运行目录深度。
原文读数 `s55_2_ci_key_shape.txt`（run 40275791754 的 logs zip，`4_backend.txt`）。
上面两行标"手造"的输入是我为"归一只换形状、不放松匹配"造的负例，不冒充 CI 读数。

最后一行是这条判据的关键不对称：**归一只换形状，不放松匹配**——否则会退化成子串匹配，
模块改名或被人塞一个同名文件都不会红。倒数第二行则是规划方裁给本卡的顺带修（D 之外那半句：
"旧 `_match` 同名前后缀只返回 1 个的静默面，算 STEP-55 顺带修掉、写清楚就行、不另登记 P 号"）：
旧实现因为要求前导斜杠，`app/services/kb.py` 与 `other/app/services/kb.py` 同时存在时只会命中后者
（1 个 ⇒ 门以为判过了，实际审的是别的文件）；现在返回 2 个并由调用方判 NOT-PASS。

真机复算（同一份 @win 生成的 `coverage.json`，命令按改后的附录 A：仓库根 + `--json apps/api/coverage.json`）：
改前 rc=2（8 条失配，原文 `s55_2_pre_fix_rc2.txt`），改后 rc=0 且 8 条各恰命中 1 个（`gates.txt` 末段八行"达标"）。
@linux 键形的复算：用脚本把 `coverage.json` 的 `files` 键解析后归一为 `app/services/kb.py` 形再喂给门 ⇒ rc=0
（**这里我第一次做错了一次**：先用文本把 `\` 换成 `/`，JSON 里的转义 `\\` 变成 `//`，门判 rc=2——
那是我的副本错，不是门错；改成解析后重键才对。教训记在这里，因为它正是"自造输入会撒谎"那一族。）
真正的 @linux 读数由 CI 给（这道门只在 ubuntu job 上跑，`ci-windows.yml` 无该步）。

### 其二：控制台编码（同一条命令、同一个文件，规划方只知其一）

键形修好后，附录 A 那条命令**照原样**在本机仍 rc=1：末行 `✅ 全部模块与全局达标` 的 U+2705 不在 cp936 里，
八个模块逐行"达标"都印出来了，然后在末行抛 `UnicodeEncodeError`。这不是判据问题，是这台机器的
控制台语言在决定门的结果——而卡面 3 目标②写的是"本机任何平台都能按附录 A 原样复算"。
修法：脚本 `__main__` 段把 stdout 钉成 utf-8（判红那侧的 `❌` 同样编不出来，真判红时连诊断一起崩，
所以这条两侧都受益）；放 `__main__` 而非 `main()`，因为 in-process 单测走 capsys，脚本不该改测试进程的流编码。
常驻用例 `test_gate_survives_a_non_utf8_console` 用 `PYTHONIOENCODING=gbk` 起子进程跑真脚本
（Linux 也有 gbk 码表，不依赖本机 locale），断言 rc=0 **且** stdout 真含"全部模块与全局达标"那行。
先红与逐字读数见 `s55_2_cp936_before_after.md`（含"同机同不设变量跑 `check_docs_consistency.py` ⇒ rc=0，
所以这不是所有门的通病"那条核实）。

### 用例规模

`apps/api/tests/test_module_coverage_gate.py`：S55.2 键形四条 + 编码一条 ⇒ **16 passed**（原 11）。
全部不连库 ⇒ `SKIP_BASELINE`(6) 与 `SKIP_BASELINE_WIN`(692) 都不动。

## S55.3 30101 注释纠真（P-123 余项 / D-V21-14）

只动注释与文案旁的说明，不删码、不改判断分支：

| 文件 | 改动 |
|---|---|
| `apps/web/lib/api/spaces.ts:48-51` | `getSpace` 的注释从"不存在/无权（30101/10102）"改为"（30004）"，并注明依据（后端全仓不产 30101、`test_spaces_api.py:244` 的断言钉 30004） |
| `apps/web/lib/api/types.ts:409-413` | 30101 那条文案**保留**（键行 413 一字未动），上面加四行说明：僵尸文案、仅为旧客户端兼容、线上未找到是 30004、删除另排卡（D-V21-14 的"发版前不删"） |

前端仍在三处并列判断 `30004 || 30101`（`PublicLibraryPicker.tsx:66`、`SubscribeShortcut.tsx:53`、
`useSubscriptions.ts:135`）与 `useSpaceDetail.ts:169` 的三码并列——按裁决**本卡一律不动**，
删除与收敛另排（那要连着改测试与组件，不该挤在发版前）。

## 审查 nits 的逐条处置

第 1 轮子智能体审查结论 **PASS（带 nits）**；下表每条给"处置"与证据位置。

| # | nit | 处置 | 证据 |
|---|---|---|---|
| 1 | `checkShape` 有几处"今天走不到"的静默面（对象缺 `additionalProperties`、数组缺 `items`、`$ref` 带同级键） | **本轮关掉**：`auditDefs` 装载即抛，四条各有红用例 | `s55_1_checker_blindspot_audit.txt`、探针表下方①② |
| 2 | `enum` 判在 `type` 之前 | **不改，理由量化**：三处 enum 全带 `type:string` 且允许值全是字符串，`includes` 对非字符串必不成立 | 同上 ③ |
| 3 | `minimum/maximum/minLength/maxLength` 被当注解忽略 | **本轮关掉**（并入标量层）：为把它塞进卡面的 ≤80 行预算，核对器把 `enum`/数组 `forEach`/类型不符三处两行写法合成一行，最终 **78 行**；探针 C 证它活 | `s55_1_checker_sizes.txt`、`s55_probe_c_s55.txt` |
| 4 | `key in obj` 走原型链 | **本轮关掉**：三处改用 `own()`（行数不变）；`auditDefs` 另把"属性名撞 `Object.prototype`"判成装载期硬错 | 现测撞名 0 个（审计文件①） |
| 5 | 只断言"匹配到一条路由"，没断言"匹配到这条" | **本轮关掉**：加 `normalizeRouteKey` 逐条比对；D 行反证 | `s55_probe_d_s55.txt` |
| 6 | `ROUTE_OVERRIDES` 的旧键被静默忽略 | **本轮关掉**：加"每个输入键都必须在对照表里"的断言；E 行反证 | `s55_probe_e_s55.txt` |
| 7 | "`_match` 同名前后缀只返回 1 个"的旧静默面 | **按规划方裁决算本卡顺带修**，不另登记 P 号；写法与判据已写在 S55.2 其一的倒数第二段 | `s55_2_old_vs_new_match.txt` |
| 8 | "改后 @win rc=0"依赖 UTF-8 stdout，默认 cp936 控制台会崩在末行 ⇒ rc=1 | **成立，已按上面"其二"就地修**（这条不是读数脚注，是卡面目标②没达成）；并补常驻用例 + 先红 | `s55_2_cp936_before_after.md`、探针 F |
| 9 | 我自己追问出来的一条（审查没点名）：`checkShape` 里 enum 判在 type/范围之前并直接 return，**同一节点同时写 enum 与范围键**时范围判据会被跳过 | **不修，量化后如实登记**：现测 3 个 enum 节点的键集都只有 `description/enum/type`，与范围键的交集为 0 ⇒ 今天走不到；这是"顺序造成的静默面"，写进审计第⑤段而不是注释里的一句话 | `s55_1_checker_blindspot_audit.txt` ⑤ |
| 10 | 又一条自己追问的：白名单里 `$defs`/`$schema`/`$id` 被当注解忽略，若某个 def 自己再带一层 `$defs`，那一层没人核对 | **由构造保证，不靠运气**：生成器 `scripts/gen_contracts.py:255` 对每个模型 `sub.pop("$defs", {})` 把嵌套定义搬到根（:258-261 键冲突即 error），`:315-316` 又拒掉一切非 `#/$defs/<名>` 的引用；现测 `$defs`/`not`/`oneOf`/`allOf`/`if`/`then`/`patternProperties`/`const` 在两份 schema 的 def 递归里命中总数 0 | 同上 ⑥ |
| 11 | `anyOf` 取"第一个满足的分支"，若同层有两条结构分支就会挑到松的那条 | **量化后成立可用**：全部 `anyOf` 里含 2 条以上 object 分支的 0 处、含 2 条以上 `$ref` 分支的 0 处（可空位都是一对一）⇒ 今天顺序无关；出现多结构分支的那天必须改判据 | 同上 ⑦ |

未处理并如实留下的只有一条：`pattern`/`format` 仍只当注解忽略。现测这两位在两份 schema 里各 0 处，
所以今天没有"已声明却未判"的约束；等它们真出现时，`checkShape` 的行数预算与这道门的判据面要一起重开
（不登记 P 号，因为没有待修的缺陷——登记的是上面这条已被量化的边界，供下一版判断）。

### 第 2 轮审查（对增量再审一次）的处置

结论同样是 **PASS-with-nits**（子智能体另附一句"没能在今天的字节上造出假红/假绿"），四条潜在面 + 六条文字失真，
逐条：

| # | 第 2 轮 nits | 处置 | 证据 |
|---|---|---|---|
| 1 | `auditDefs` 判"同级结构键"用的豁免名单里还留着 `minimum` 等范围键，而核对器**已经**在判它们 ⇒ `$ref` + `minimum` 会被当注解放过；`anyOf` 带同级键也没管 | **本轮关掉**：拆成 `ANNOTATION_ONLY`（真注解）与 `BOUNDS`（被判的范围族），豁免只看前者；并加 `anyOf` 同级结构键一条。现测两类各 0 处 | `s55_1_checker_blindspot_audit.txt` ⑧、探针批表 |
| 2 | `required` 的键不在 `properties` 时，`additionalProperties:false` 会把**正确**样例判红（假红方向），体检没管 | **本轮关掉**：装载期硬抛；现测 0 处 | 同上 ⑧ + 自检 toThrow |
| 3 | `checkShape` 只在被走到的层判"认不出就抛" ⇒ 可选键没填时那下面的 `oneOf`/`const`/`patternProperties` 永远不会被 visit | **本轮关掉**：把 KNOWN 判据搬进 `auditDefs` 做全树判（`checkShape` 那侧照旧保留，两处都抛） | 同上 ⑧ + 自检 toThrow（`oneOf` 负例） |
| 4 | `paramNames` 判据被 `if (paramNames?.length)` 包着 ⇒ "把某条的 paramNames 删掉"这一刀整条跳过；另外 22 发一律传空 search，分页"回显"那条腿从没走过 | **本轮关掉**：改数 pattern 里的真实捕获组（`\(` 后不是 `?`）；并加一发带 `limit=7&offset=3` 的分页探针。反证 G/H 各自红 | `s55_probe_readings.md` G/H 行 |
| 5-10 | 一批文字失真：探针 sha 与交付字节不符、"`❌` 那侧会崩"没有裸读数、`loadDefs` 14→15、"10/10"实际 11 步、"三份 red"实际五份、测试 docstring 指了 `.txt` 而文件是 `.md`、"23 次分发"变 24 | **逐条改**：探针批 A–H 在最终字节上重跑并前后核 sha（`sha_all_equal=True`）；F 加跑判红那侧拿到 `'gbk' codec can't encode character '\u274c'` 的原文；其余数字按现值订正，docstring 的锚改成 `.md` | `s55_probe_readings.md`、`s55p2_f_red_plain_console.txt`、`s55_1_checker_sizes.txt` |
| — | 还有一条要认错：H 探针我第一次锚到了另一个分页壳，跑出 **rc=0**（看起来像"判据没问题"） | 那次不算证据，锚点对到 `GET /api/v1/spaces` 的壳才是 rc=1；两次都写进反证批的"三点如实" | `s55_probe_readings.md` 第 2 点 |

## 本机门链（按 CI 顺序，三跑都存原文）

| 跑 | 原文 | 树 | 读数 |
|---|---|---|---|
| 第 1 跑 | `s55_local_gates_pass1.txt` | 审查改动**之前**的树 | **11 步 rc_* 全 0**：ruff 0、mypy 0（134 文件）、alembic heads 单头 `ab1006c2a`、`gen_contracts --check` 0、`check_docs_consistency` 0、pytest **2470 passed / 6 skipped / 4 deselected / 0 failed**（1286.41s，TOTAL 88.94%）、覆盖率门 0、前端 tsc 0、contracts tsc 0、vitest **53 文件 425 passed**、lint 0。**这一步漏跑了 `alembic upgrade head`**（STEP-54 有跑），属我这一步复现不全 |
| 第 2 跑 | `s55_local_gates_pass2.txt` | 把审查 nits 折进来后的树 | **ruff 1 / mypy 1 / pytest 1（1 failed, 2470 passed）**——三条红都指向我自己的新代码：① `import subprocess`/`import sys` 我先写在函数内又提到模块级 ⇒ ruff `F401` ×2，而 `tests/test_workflow_gate_wiring.py:98` 会跑 `entry.py lint-backend`，于是全量连带一条红；② `sys.stdout.reconfigure(...)` 直写 ⇒ mypy `union-attr`（`sys.stdout` 的类型是抽象 `TextIO`）。跑到前端第 1 步时会话被中断，链未走完 |
| 最终跑 | `s55_local_gates_final.txt` | 交付字节（含第 2 跑的修复 + 第二轮 nits） | **13 步里 12 步 rc=0，1 步是我的调用形错**：ruff 0、mypy 0（134 文件）、alembic upgrade head 0、alembic heads 单头 `ab1006c2a` 0、`gen_contracts --check` 0、`check_docs_consistency` 0、pytest **2471 passed / 6 skipped / 4 deselected / 0 failed**（1258.94s）、覆盖率门 0（**按附录 A 原样、不设 `PYTHONIOENCODING`**：8 条各恰命中 1 个、TOTAL 88.90%、末行 `✅ 全部模块与全局达标` 正常打印）、前端 tsc 0、vitest **53 文件 425 passed**、lint 0（无警告）、演示态 build 0、**mock e2e 31 passed**；唯一那条红见下一行 |
| ↑ 的红那步 | `s55_pkg_tsc_ci_form.txt` | 同上 | `rc_pkg_tsc=1` 不是类型错，是 `Command "tsc" not found`：我这条链用 `cd packages/contracts && pnpm exec tsc`，那个 workspace 没装本地 tsc。CI 的形是 `ci.yml:382` 的 `pnpm exec tsc --noEmit -p ../../packages/contracts/tsconfig.json`（从 apps/web 打），照它复跑 **rc=0、输出 0 字节**。⇒ 记两件事：①链脚本已改成 CI 形；②第 1 跑同一步曾 rc=0，说明我这一步的调用形在两次跑里不是同一个东西——**"有时能跑有时报没找到"的门等于没有门**，所以这条不当巧合放过去 |

两处红的归属要说清楚，因为它们都不是本卡判据的问题：第 2 跑的 ruff/mypy 是我这条改动自己引入的静态面失配，
修法是删函数内重复 import + 给 `reconfigure` 套 `isinstance(sys.stdout, io.TextIOWrapper)` 收窄
（理由与逐字读数在 `s55_2_cp936_before_after.md` §修法）；修后这两条各自复跑 0，
且 `test_module_coverage_gate.py` + `test_workflow_gate_wiring.py` 一并 **20 passed**。
这也说明第 1 跑的"11 步全 0"不是走过运气的读数——门确实在下一步把我自己的错抓住了。

## S55.4 提交、三绿与闭合（收口批回填）

交付批 `4a2c62b`（`e4a9a67..4a2c62b`，推送后 `origin/main...HEAD` = `0 0`）。
门禁串联口径照纪律：`guard-ports && guard-structure && guard-versions && guard-ci-secret-mask && evidence-check && git add && git commit && rounds-check && evidence-check`，
一步失败就不往下走；`evidence-check` 在 `git add` **之前**跑是 rc=3（"前置门在本批没有可检面"，因为 diff 基线取不到未跟踪文件），
这条第三态不当通过也不当失败，所以按既有做法先 stage 再复跑，两道都过才提交：

```
evidence_after_add_rc=0        前置两道门（D-V4-03 耦合 + 敏感形）+ stdlib 证据复跑 + ruff + gitleaks（441 commits，no leaks）
rounds-check                   范围内 1 个提交，阈值 ≤2 ⇒ ✅
post_commit_gates 后 evidence-check 再一次 ⇒ ✅
```

@ci 三绿（同一 head `4a2c62b`，全部 attempt 1，`s55_ci_run_status.txt`）：

| 工作流 | run | 结论 | 判据读数 |
|---|---|---|---|
| CI | 40320739120 | success | `2471 passed / 6 skipped / 4 deselected`（243.27s）、skip 门禁 `total_skipped=6 baseline=6 pg_unreachable=0`、`Total coverage: 88.92%`、**模块覆盖率门 ✅ 全部模块与全局达标**（@linux 键形＝相对正斜杠，见 `s55_2_ci_key_shape.txt`）、前端 vitest `53 文件 / 425 passed`、mock e2e `31 passed`（`s55_ci_backend_readings.txt`） |
| CI-Windows | 40320739123 | success | `failed=0 total_skipped=692 baseline=692`（零余量对齐，本卡新增 5 条用例都不连库 ⇒ 692 不动）、前端 `53 文件 / 425 passed` 与 CI 侧、本机侧**逐字同数**（`s55_ci_windows_readings.txt`） |
| Security | 40320739138 | success | 整条 success（pip-audit / pnpm audit / gitleaks / guard 步，与前三卡同口径） |

本机 vs CI 的对照（这是"全量 + 三绿"里"全量"两个字的实际含义）：本机最终跑 `2471 passed / 6 skipped / 4 deselected`
= CI `2471 / 6 / 4`；本机 vitest `53/425` = CI 两侧 `53/425`；本机 mock e2e `31 passed` = CI `31 passed`；
覆盖率 TOTAL 本机 88.90% vs CI 88.92%（±0.03 在既有的抖动带内，AGENTS.md 测试段记过这条）。
差异只在两处且都如实归档：本机跑的是**跨会话持久库**（STEP-54 修的那条在这台机器上连跑才判得出确定性），
CI 是**新库**；本机那条 `rc_pkg_tsc=1` 是我的调用形，CI 用 `ci.yml:382` 的形跑过了。

P 号闭合：P-124（摘 satisfies 两道门看不见 ⇒ 现在有第四道运行时门，反证 A 行红在最终字节上）、
P-125（@win 不可复算 ⇒ 键形 + 编码两条因都修了，附录 A 原样命令本机 rc=0，"待确认"的键形差异已定为 `os.sep`）、
P-123 余项（`spaces.ts` 注释与 `types.ts` 僵尸文案说明；发版前不删码，按 D-V21-14）。
新登记的 P 号见台账 **P-126**（STEP-46/47 的独立复查提前跑出来的覆盖面缺口，不阻塞 v1.1.3）。
推送凭据口径与一处需要更正的历史说法见 `s55_push_credential_note.md`；本机环境与进程事故见 `s55_local_env_note.md`。
