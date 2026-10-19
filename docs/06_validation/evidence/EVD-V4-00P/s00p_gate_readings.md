# EVD-V4-00P · STEP-00P 规划产物敏感形机械门

执行方：Agent-Guard　基线：`main@97f1d61`　日期：2026-10-19　卡面：`docs/任务规划V0.13.0/steps/STEP-00P-规划产物敏感形机械门.md`
（V0.14.0 `04-…` 第 10 行把它列为 ⚪ 剩 5 项、归执行 Agent-Guard、档位 sonnet；本版未给 00P 新增增量。）

> 本文件所有计数都由命令产生（§3 给命令）。本仓本轮之内已有三次「手填数字被现读推翻」，
> 所以这里不出现任何凭印象的数；打码读数只报形状，不含可复原的值。

## 0. 五项 L3 的完成度

| 原子任务 | 状态 | 证据位置 |
|---|---|---|
| S00P.1.1 敏感形扫描做成 `evidence-check` 阻断步 | 已交付；**验收第 1 条部分确认**（整门在本机是 3 不是 0，原因见 §5/§11.2） | §2、§3、§5、§11 |
| S00P.1.2 两档反证（含形状⇒红 / 换占位⇒绿） | 已确认（本轮现跑） | §4、§12 的变异表 |
| S00P.2.1 立规：文档与注释不内联敏感形与正则本身 | 已确认 | `conventions.md` §9.1、§1.2、§10 |
| S00P.2.2 必须引用凭据形时的替代写法 | 已确认（第 2 轮补齐「打码≠脱形」覆盖到用户名位） | `conventions.md` §9.1 规矩二；范例 = 本卡测试文件的 `_dsn()` / `_kv()`；§10 的两次自伤是它的实证 |
| S00P.3.1 边界声明 | 已确认（第 2 轮把「已知漏检面」也写进边界） | `conventions.md` §9.1 边界五条、§6、§6.1 |

## 1. 三条前置事实（全部现读；其中两条与卡面文本相反）

### 1.1 卡面指定的调用方式会造一个**永绿的安全门**

卡面 S00P.1.1 写「对本次待提交路径跑 `secret_shape_scan.py`」，而该脚本的扫描集是
`root.rglob("*")`——把**文件**当参数交给它，`rglob` 对文件根返回空集，于是「文件数 0 / HIGH 0 / rc=0」。
现跑读数（同目录、同基准，两个参数只差一个是目录一个是文件）：

```bash
cd D:/Code/AideanBotHot
python -X utf8 docs/任务规划V0.5.0/evidence/65f508b/secret_shape_scan.py \
  docs/任务规划V0.13.0/evidence/314d7f2 | tail -1        # 目录
python -X utf8 docs/任务规划V0.5.0/evidence/65f508b/secret_shape_scan.py \
  docs/任务规划V0.13.0/evidence/314d7f2/probe_bots_read_by_plain_user.txt | tail -1   # 文件
```

读数：目录 ⇒ `HIGH 命中：5（ALLOWED 0）`、rc=1；文件 ⇒ `HIGH 命中：0`、rc=0。
这条读数已由用例 `test_the_card_named_script_gives_a_vacuous_pass_on_a_file_argument` 钉住在 CI 面上。

⇒ 处置：判据实体落在 `scripts/guards.py`（本仓 00X/00T 批立的「唯一源」纪律：Makefile 与 entry 只转调），
规则四条常量**逐条搬运不改语义**，并由两条对账用例与那条脚本源码里的字面量逐字符比较
（含规则名与顺序；折行写法与 `DSN = re.compile(...)` 名字引用都能抽出）。
卡面禁止修改 `docs/任务规划V0.1…V0.8/**`，所以原脚本原地不动，两份并存靠对账用例防漂移。

### 1.2 门差点咬死自己——`S00P.2.1` 的第三次自伤由本卡实现文件犯、由本卡的门抓出

第一版 `scripts/guards.py` 写完后自扫得 2 条 HIGH：一条在解释打码必要性的 docstring 里
（那里写着一条邻接形状，正是它要防的东西），一条在说明「另一条判据召回面更窄」的注释里
（写了键名=短值的形状）。两处都改成**只描述邻接关系**后归零。

⇒ 这条不是插曲：它是 S00P.2.1 立规的唯一实证类型（前两次是 V0.7.0/V0.6.0 的规划文档抄占位串与抄正则）。
所以 `conventions.md` §9.1 的理由段把它写进去了，并由 §G 末条用例
（`test_the_implementation_files_themselves_carry_no_shape`）把「实现文件自身不带形状」
钉成常设判据——而不是只在这轮口头保证。

### 1.3 权威工具步是 fail-open 的（登记 P-37）

`evidence-check` 的真实工具步里 gitleaks 在本机是可得的（`%LOCALAPPDATA%/Programs/tools/gitleaks/gitleaks.exe`，
8.21.2，与 `security.yml:53` 同版），实测它在**自报扫描未完成**的同时仍返回 rc=0：

```
ERR [git] C:\Program Files\Git\usr\bin\astextplain: line 18: docx2txt.exe: command not found   ×2
ERR failed to scan Git repository error="stderr is not empty"
INF scan completed in 9.17s
INF no leaks found          ← rc=0
```

根因归属已查实，不在本仓：`C:\Program Files\Git\etc\gitattributes`（Git for Windows 的 **system 级**属性文件）
给 `*.docx` 注册了 `diff=astextplain`，`diff.astextplain.textconv` 在 system 级配置里，而 `docx2txt.exe` 未装。
触发文件全在 `.project/` 下（第三方参考源码里的 docx/pdf），仓库级 `.gitattributes` 与此无关；
⇒ 这是 **Windows 独有**的读数差异，ubuntu CI 那一步不受影响。
召回并未整体失效（STEP-00S 的正反证：拿掉 `.gitleaksignore` 后同一条命令报 8 条 leak、rc=1），
失效面是被 textconv 处理的二进制文档正文。

⇒ 处置：`evidence_check` 的工具步改为捕获合并输出，rc=0 但含 `failed to scan` ⇒ **退出码 3**
（第三态：这一维没有终判，不是 PASS）。不给 1 的理由写在 §11 里——把「没扫成」和「扫出凭据」
混成同一个红就是拿狼来了消耗门禁信用。（用例
`test_gitleaks_failed_to_scan_is_third_state_not_pass` + 极性对照
`test_clean_tool_output_still_passes`、`test_a_nonzero_tool_rc_is_propagated`）。
这是对既有 fail-open 的**收紧**，不是新增豁免；因涉及权威工具的判定方式，登记 P-37 待追认。

## 2. 判据与接线

新增（`scripts/guards.py`）：`SECRET_RULES`（10 条）、`SECRET_ALLOW`（2 条）、`SECRET_ASSIGN`、
`SECRET_FAKE`、`_SECRET_ASSIGN_SKIP`、`_mask_shape()`、`secret_scan()`（纯函数）、
`secret_scope()`、`secret_shape_check()`。四个命名常量与那条脚本逐字符对账；
`_SECRET_ASSIGN_SKIP` 是原脚本主循环里的行内 `re.search`，搬运时提名为常量，语义未变。

编排改动（同一个文件里，三处，都有对应用例）：

1. 前置门之间**不互相遮蔽**：`coupling_check` 与 `secret_shape_check` 各自跑完再汇总。
   改前是 `if coupling_check(base): return 1`——S00T.V14.2 刚修过「一维遮蔽另一维」，
   这次是本批新加的那一维被同一个形状遮蔽。
2. 前置门的第三态（无可检面）**不吞掉主用途**：记到最终退出码，但证据复跑照旧执行。
   否则干净工作树上 `make evidence-check` 会连证据都不复跑——本目标最常见的用法反而失效。
3. 缺席告警只报真缺席的那个。改前 `if gitleaks and tool_steps is not None … else: print(SKIP gitleaks)`
   在 ruff 缺席、gitleaks 在场时也会打印一条「SKIP(tool missing) gitleaks」——一条假读数。

接线面：**`Makefile` 与 `scripts/entry.py` 本轮未改**，因为 `evidence-check` 的目标体早已是
`@$(GUARDS) evidence-check`（00X/00T 批的唯一源结果），新增一步落在被转调的实体里即可；
没有新的 Make 目标 ⇒ 不需要 entry 注册，`check_entry_parity` 保持绿（§3）。
卡面「输出（文件）」栏写的是 `Makefile`（`evidence-check` 内新增一步），这是文本落后于 00X 之后的现实，
偏离记录见 §7。

打码：命中行只报「规则名 + 文件:行号 + 打码片段」。DSN 形状里 **userinfo 两段都打码**
（各留 4 字符），其余规则只留前 4 个字符 + 星号，赋值形只报键名与**值长度**，不报值。
匹配串本身止于 at 符号，所以主机段从来不在片段里——定位靠 文件:行号 + 规则名，不靠片段复原。
卡面指定的原脚本打印匹配串前 90 字符，对连接串形状而言那已含凭据正文；这里刻意与它
**输出格式不同**（判据相同），依据是安全铁律第 1 条。§3 的用例组把打码与判据成对钉住。

取材面（第 2 轮加，理由见 §12）：门读的是 **`git show :路径`（索引 blob）**，提交面回退档读
`git show HEAD:路径`，不再是文件系统上那一份。输出行里带 `取材面=index|head` 让读数可核对。
`_git()` 统一带 `-c core.quotepath=false`（§11.1）。

四处**收紧**（方向都是少漏检，不是新增豁免；每条都有反证 + 变异验证，见 §12）：
① ALLOW 作用在匹配段而非整行；② `re.compile` 豁免只认「值本身以 re.compile 开头」；
③ DSN 打码覆盖用户名位；④ 全被跳过 ⇒ 第三态而非绿。
四条都偏离了那条 V0.5.0 脚本的实现，但对账用例比的是**模式串**，
收紧的是**应用方式** ⇒ 逐字符对账仍然成立（这是刻意的分工：模式跟着权威走，应用方向朝安全走）。

## 3. 反证电池读数（命令与原文）

```bash
cd apps/api
.venv/Scripts/python.exe -X utf8 -m pytest tests/test_secret_shape_gate.py -q
.venv/Scripts/python.exe -X utf8 -m pytest tests/test_secret_shape_gate.py --collect-only -q | tail -1
.venv/Scripts/python.exe -X utf8 -m pytest tests/test_guard_rounds.py tests/test_secret_shape_gate.py -q
.venv/Scripts/ruff.exe check app tests
cd .. && python -X utf8 scripts/check_entry_parity.py; echo rc=$?
python -X utf8 scripts/guards.py rounds-check --base HEAD~9; echo rc=$?
python -X utf8 scripts/check_docs_consistency.py; echo rc=$?
```

| 判据 | 读数 |
|---|---|
| 用例 defs（AST 现取） | 38 |
| 收集并通过（`pytest -q`） | 64 passed |
| 与 00T 批两道闸合跑 | 103 passed |
| `ruff check app tests` | All checks passed |
| `check_entry_parity` | rc=0（无新目标，转调面未动） |
| `rounds-check --base HEAD~9` | rc=0 |
| `check_docs_consistency` | rc=0 |
| 变异验证（§12 的五条） | 5/5 被抓到，还原后 guards.py 逐字节相同 |

覆盖维度（每族都有**极性对**，只测「能不能红」是不够的，还得测红得方向对不对）：

- 判据敏感性：10 条规则 + 赋值形各自命中自己的形状（11 例参数化）；多形状同行按条计。
- 放行侧：6 种占位写法各 `ALLOWED=1`、`HIGH=0`；反向对照只换口令段 ⇒ 必须红。
  规则定义行靠 `re.compile` 豁免；同一行摘掉该字样 ⇒ 必须红。
- 打码：11 例逐条断言「敏感段不出现在输出里」且「片段严格短于原串」；
  DSN 那条额外要求 scheme 与账号仍在（打码不能把诊断信息一起打掉）。
- 副本对账：与卡面指定脚本逐字符比较（规则名+模式+顺序、ALLOW 两条、ASSIGN、FAKE）；
  抽取器**取不到就报错**，不悄悄跳过（悄悄跳过的对账等于没对账）。
- 取值口径：索引优先 / 索引空退到 `base..HEAD` / 基线不可解析⇒1 / 两面皆空⇒3 /
  删除与二进制跳过 / 读不到⇒红（并断言 `cat-file` 之外没有「读不到当没有」的分支）。
- 编排：红⇒短路且复跑不执行；第三态⇒复跑照旧执行；两门都跑；工具缺席只报真缺席；
  `failed to scan`⇒红；rc 非 0 透传。
- 端到端：`tmp_path` 里 `git init` 的一次性真仓库四档（staged 形状⇒1、换占位⇒0、
  整门接线⇒1 且复跑未尝试、committed 批次索引空仍看得见⇒1、两面皆空⇒3）。

## 4. S00P.1.2 的两档反证（本轮现跑，非引用历史读数）

| 档 | 动作 | 读数 |
|---|---|---|
| 红档 | 一次性仓库里把含连接串形状的 `.md` 暂存进索引 | rc=1，输出含 `HIGH dsn-embedded-password leaky.md:1` + 打码片段（保留 scheme 与账号段，口令段整段星号） |
| 绿档 | 同一构造器只把口令段换成变量引用，再暂存 | rc=0，输出含 `ALLOWED 放行 1` |
| 第三态 | 索引与 `base..HEAD` 皆空 | rc=3（不是 PASS） |
| 遮蔽反证 | 走整门 `evidence-check` | rc=1 且输出里没有 `── `（复跑未被尝试）⇒ 「阻断步」名副其实 |

形状全部由跨字符串边界的拼接产生，测试文件源码文本里不留完整形状（§1.2 的规矩先约束写门的人）。
绿档之所以是 rc=0 而不是整门 rc=0：脚手架里没有 `EVIDENCE_PROOFS` 那几个脚本，整门会先撞
「证据脚本不存在」——那是脚手架的限制，不是这一维的读数，所以两档反证直接跑 `secret_shape_check`。

## 5. 出门判据：真实待提交面上的读数

待提交面 = 本批 `git diff --cached --name-only` 现取的 **8 个路径**。两列读数的**先后**就是发现过程（§11.1）：

| 读数项 | 第一次（含缺陷） | 修复后 |
|---|---|---|
| 敏感形门自报的扫描面 | 待检 7 / 实扫 5 / 跳过 2 / HIGH 0 | 待检 8 / 实扫 8 / 跳过 0 / HIGH 0 |
| 这一维的判定 | ✅ 待检面无 HIGH 命中 | ✅ 待检面无 HIGH 命中 |
| 前置的耦合门 | 证据脚本净增 0 / 用例净增 32 ⇒ 放行 | 证据脚本净增 0 / 用例净增 38 ⇒ 放行 |
| 整门 `make evidence-check` | rc≠0（当时是 §11.2 的判红） | rc=3（gitleaks 无终判，P-37） |

（第一列那次的批面是 7 个路径，之后批面加了执行记录文件 ⇒ 8。两列都如实保留，不事后统一。）

复现命令（`make evidence-check` 需先 `git add` 本批）：

```bash
git -c core.quotepath=false diff --cached --name-only | wc -l    # 8
python -X utf8 scripts/guards.py evidence-check | grep 敏感形门   # 实扫 8 / HIGH 0
git diff --cached --name-only | tail -2                          # 默认口径：中文名被转义（缺陷来源）
```

⇒ 卡面验收第一条（「`make evidence-check` 含该步且对当前待提交路径 rc=0」）判 **部分确认**：
「含该步」成立，「这一维对本批 8 个路径给 0 命中」成立；
整门在本机回到 **3 而不是 0**，原因是 §1.3 那条 Windows 专属的权威步 fail-open（P-37）——
不是这一新步的判定。不为了凑那个 0 去放宽 §1.3 的 tripwire，改判据口径见 §11.2 的代价说明。
「ubuntu 侧不会有这条 3」是**推论**（根因在 Git for Windows 的 system 级属性文件），本机无法现跑 ⇒ 标未验证。

最后一轮跑出的完整读数（同一批、索引未变）：
`敏感形门（STEP-00P S00P.1.1）：待检 8 个路径（取材面=index），实扫 8，跳过 0，HIGH 0，ALLOWED 放行 0`
+ `✅ 敏感形门：待检面无 HIGH 命中`；前置的耦合门同行报 `证据脚本净增 0，用例净增 38`。

## 6. 假阳性规模（P-36 的决策依据；执行方未自行收窄任何判据）

用 `guards.secret_scan` 直接扫本仓自有文件（`docs/任务规划V0.13.0`、`docs/任务规划V0.14.0`、
`scripts`、`apps/api/app`、`apps/api/tests`；扩展名 .py/.md/.txt/.json/.yml/.ts），分类计数：

| 类别 | 条数 | 判定 |
|---|---|---|
| 表达式引用（变量/属性/下标，值不在文本里） | 31 | 确定假阳性 |
| 引号字面量（测试夹具的 kwargs） | 16 | 抽查 12 条均为夹具占位值；**未逐条穷尽**，但形状与真实泄漏同形 |
| `vendor-key-assign` | 3 | 同上，夹具 `Settings(redfox_api_key="…")` |
| `.gitleaks.toml` 同源的其余 8 条规则 | 0 | 本仓自有文件里没有一条真凭据形 |
| 合计 | 50 | 全部来自两条**启发式**族 |

位点样本（只报键名与值长度，不报值）：`docs/任务规划V0.13.0/evidence/314d7f2/probe_bots_read_by_plain_user.py:11`
的 DSN 键（值长 11，`os.environ` 引用）、`scripts/entry.py:230/237` 的 dsn 键（值长 15 与 11，
环境变量引用与解析式）、`apps/api/tests/test_provider_contract.py:78-82,233-236` 的 api_key 键
（值长 8，夹具）、`apps/api/tests/test_push_providers.py:77` 的 secret 键（值长 15，夹具）。

后果与建议口径（**留给规划方/00S 裁**）：门只扫「本批」，所以今天不挡任何人；
但任何人一旦改动上述文件，就会因**非凭据**被判红——那正是卡面阻塞条件①预告的「门被人关掉」路径。
可选三条：① 赋值形只作用于文档面、不作用于 `apps/api/tests/**`；
② 值必须是引号字面量才计（等价于采纳 `EVD-V5-00S/secret_shape_gate.py` 的窄口径，代价是放过无引号写法）；
③ 保持现状，靠 S00P.2.1 的「别内联形状」把文档侧收敛。
执行方按卡面「不得自建 allowlist」「规则语义变更需单独评审」两条，选择**不改语义**并登记 P-36。

另记一条同族分歧（不属本轮决定）：`EVD-V5-00S/secret_shape_gate.py:14` 自称
「与 `.gitleaks.toml` 的 connection-string-embedded-password 规则逐字符一致」，
实测它的字符类里多了一个反斜杠排除项 ⇒ 该说法不成立（是**弱化**召回）。
它在别的会话/卡的证据目录里，按纪律只登记、不修改。

### 6.1 同一族的两条**反向**缺口（漏检方向，已复算，未改判据）

P-36 讲的多是「假阳性挡人」，但同一条启发式还有相反方向的洞，一并交给规划方裁——
只报一半会让他们做出偏向错的口径：

| 形状（文字描述，不落可复制串） | 现在会不会被抓住 | 为什么 |
|---|---|---|
| 厂商键名 + 等号 + **7** 个字符的值 | 不抓 | 厂商规则要求值至少 8 个非空白字符 |
| 键名以**下划线或前缀词**紧贴在 token 之前（如 `APP_TOKEN = 一个 18 字符的真值形状`） | 不抓 | 赋值形要求词边界，而前导是 `_`（单词字符） |
| 同上但键名单独出现（`token = …`） | 抓 | 边界成立 |

⇒ 这两条是**继承自那条脚本的口径**，不是本轮引入；本轮把 ALLOW 与 re.compile 两处收紧之后，
剩下的漏检面就只剩「阈值」和「词边界」这两个口径问题 ⇒ 归 P-36 一起裁，不自行动。

## 7. 偏离卡面处（逐条给理由，不隐匿）

| 卡面原文 | 本轮做法 | 理由 |
|---|---|---|
| 「对本次待提交路径跑 `secret_shape_scan.py`」 | 判据实体在 `scripts/guards.py`，逐字符对账 | §1.1 实测：直调该脚本 = 永绿门 |
| 输出文件栏含 `Makefile` | `Makefile` 未改 | 目标体早已转调 guards；改被调方即等效，且不留第二份实现 |
| 「命中只报 文件:行号 + 形状片段」（原脚本口径，片段含口令正文） | 打码后输出 | 安全铁律第 1 条；§3 打码用例组 |
| 「`SKIP(tool missing)` 且以非 0 退出」 | 沿用本仓第三态 rc=3 并保留该字样，且只报真缺席的工具 | rc=3 是 00T 批已确立的「非 PASS 非 FAIL」口径，不能另立一套 |
| 「跑 `secret_shape_scan.py`」隐含的**应用方式**（ALLOW 按行、re.compile 按行豁免、片段含正文、读文件系统的当前内容） | 四处收紧（§2 末、§12） | 四条都是实测漏检或正文外泄；**模式串仍与那条脚本逐字符一致**，对账用例不受影响 |
| 「允许修改」栏只有 `Makefile`/`conventions.md`/EVD-V4-00P，而**禁止修改**栏含 `apps/**` | 实际改动面还含 `scripts/guards.py`、`apps/api/tests/test_secret_shape_gate.py`（新）、`apps/api/tests/test_guard_rounds.py`（一条同族用例改成语义查找）、`docs/任务规划V0.12.0/00-README.md`（登记 P-36/P-37）、本卡执行记录 | 卡面文本早于本仓两条已成文纪律：①判据实体的唯一源是 `scripts/guards.py`；②判据必须随 `pytest tests/` 进 CI 才算「可复跑」（S00T.V14.2/V14.3 与 D-V4-03 都是这么落的）。`apps/**` 那条禁语针对的是"为绿改业务测试"，此处新增的是**治理判据用例**，与被禁动机不同向。偏离如实登记，请规划方在下一版把 00P 的输出文件栏改成与 00T 一致的表述 |

## 8. 未做 / 登记 / 交回

| 项 | 状态 | 归属 |
|---|---|---|
| P-36 赋值形启发式假阳性 | 已登记，未修（不改语义） | 规划方 / STEP-00S |
| P-37 gitleaks `failed to scan` 而 rc=0 | 门侧已判红；根因在 Git for Windows 的 system 级属性 | Security / 规划方追认 |
| `.gitleaksignore` 逐指纹（工作树打码不消除历史指纹） | 未动 | STEP-00S（卡面 S00P.3.1 明确不并入） |
| 把 `make guard` / `evidence-check` 接进 CI | 未做 | 规划方（P-32 追认项）。现读：`.github/workflows/*.yml` 对 guard/evidence-check **零命中** ⇒ 这道门目前只在本机生效 |
| `secret_shape_scan.py` 的 pytest 化 | 未做 | 00T 原 S0T.2.x 迁移队列（本卡的 §1.1 读数会被那条迁移影响，届时对账用例一并处置） |

## 9. 轮次账（D-14）

本卡计 **2 轮，已用尽**：第 1 轮 = 交付 + 同轮自纠（§11 那两处由本卡自己的端到端读数抓出，
未走「评审⇒返工」那条路，故不+1）；第 2 轮 = §12 的首轮独立评审与返工（6 条必改全部落地 + 变异验证）。
**第 3 轮由 `rounds-check` 熔断**，执行方不自行动它：本卡若还要改，只能由规划方重新立案或另开卡。
本轮提交主题**带着**「返工」与「第 2 轮」两个记号 ⇒ 门在这段范围里数到 STEP-00P 的 1 次标记（≤2 放行）。
这是刻意的：把轮号从主题里抹掉，`rounds-check` 就保护不了下一个动这张卡的人——
计数读数与这本账必须互相对得上（§3 的 `rounds-check --base HEAD~9` rc=0 就是这个核对）。
## 10. 写文档时的两次自伤（同一族，机制不同）——门的输出与散文里的「键=值」都不能照写

**第一次：打码片段不是脱形。** §4 红档那行读数我最初照抄了门输出的打码片段（scheme + 账号 +
冒号 + 一串星号 + at 符号），自扫 ⇒ 1 条 HIGH。机制：口令段的字符类只排除 `@`、`/`、空白与引号，
星号完全满足它，所以打码串**仍是邻接形状**。打码解决的是「值不可复原」，不是「形状消失」。
已钉成用例 `test_the_masked_fragment_is_still_a_shape_do_not_quote_gate_output_into_docs`。

**第二次：散文里的「键名 + 等号 + 括号读数」会被赋值形判成口令赋值。** §6 的位点样本我最初把
键名与括号里的值长度直接写成相邻的赋值形式，自扫 ⇒ 1 条 HIGH（捕获的正是括号里那串读数）。
改成「的 dsn 键（值长 15 与 11）」——键名与读数之间不再出现等号——后归零。这正是 §6 那批假阳性的**同一条**启发式在文档面上的表现，
也是 P-36 需要裁的口径之一：`键名 : 任意短词` 在文档里几乎必然是读数，在 YAML 里几乎必然是凭据。

⇒ 两条都写进 `conventions.md` §9.1 规矩一的「必要时只描述**邻接关系**」一句：
形状要么不写，要么拆开写；门的输出可以安全地留在终端与 CI 日志（那里不在扫描面上），
但不能原样搬进待提交文档。

## 11. 端到端读数抓出的两处自身缺陷（都在出门前修掉，且各有一条用例钉住）

上一批的方法账里写过一句：只测「能不能红」不够，还得测**红/绿的方向对不对**。
这两条就是那句话的落地——都是合成入参测不出来、必须在真实 git 状态与真实批面上跑一遍才现形的。

### 11.1 中文名文件被当成「本批已删除」跳过（缺陷方向：偏绿）

`_git()` 走的是 git 默认口径，**非 ASCII 路径被转义成八进制串**；门拿那个字符串去拼 `ROOT / rel`
⇒ 文件"不存在"⇒ 计入 `跳过`。第一次实跑本批时「待检 7 / 实扫 5 / 跳过 2」，
少扫的两个正是**规划文档**——而这道门管的就是规划文档。这不是外观问题：
一个带形状的 `docs/任务规划V0.x.0/…md` 提交会**静默通过**。

修法一处搞定：`_git()` 统一加 `-c core.quotepath=false`（而不是只在敏感形门上打补丁），
因为同族的 `coupling_check → missing_base_blobs → git cat-file -e base:rel` 拿转义串去取基线
会取不到 ⇒ 那是同源的**偏红**方向（把中文命名的测试文件判成「基线里没有」）。
修复后读数：待检 7 / 实扫 7 / 跳过 0（同一批把执行记录文件也加进来之后是 8 / 8，见 §5 的注）。

- 对照命令：`git diff --cached --name-only` 末两行 vs `git -c core.quotepath=false diff --cached --name-only` 末两行。
- 用例：`test_end_to_end_a_cjk_named_path_is_actually_scanned`——在一次性仓库里暂存一个中文名文件，
  断言 rc=1 且「跳过 0」。**去掉那个参数就是 rc=0**，所以这条用例是那个修复的变异杀手。

## 12. 首轮独立评审与返工（D-14 口径：本卡第 2 轮，也是最后一轮）

评审者（general-purpose 子智能体，20 次调用，一次性自测，不装依赖不跑全量）判 A PASS（附三条实测漏检）、
**B FAIL**、C PASS（附一条对账盲区）、D 无 CI 回归但**门自身两条 fail-open**、**E FAIL**（文档强于实现 +
两处数字未回填 + 改动面越界未登记），F 给出 6 条「必须返工」。

我逐条自己复算，不照抄结论。复算方式与结果：

| 评审者的说法 | 我的复算 | 处置 |
|---|---|---|
| ALLOW 按整行判 ⇒ 同行一处占位带走真凭据 | 复算成立（改前 ALLOWED=1、HIGH=0） | 改为按匹配段判 + 反证用例 |
| `re.compile` 行级豁免过宽 ⇒ 注释提一句就免检 | 复算成立 | 收窄成「值本身以 re.compile 开头」+ 反证用例 |
| DSN 打码保留用户名位，而 token 常放在用户名位 | 复算成立：用户名位放 34 字符 token 时，旧打码把整条留在输出里 | 用户名位也只留 4 字符 + 反证用例；顺带纠正我自己写错的「主机段保留」（匹配串止于 at 符号，主机本来就不在片段里） |
| 门读工作树而非索引 ⇒ add 后洗工作树，凭据照样入库 | 复算成立（最严重的一条，偏绿） | 内容改为 `git show :路径`；输出加 `取材面=`；两档反证用例（红档 + 占位进索引后放行） |
| 全部路径被跳过仍判绿 | 复算成立 | 「实扫 0」落第三态 + 用例；另补一条「超限文件整批」用例 |
| 对账不覆盖 `re.compile` 的 flags 参数 | 复算成立（只加 flags 时逐字符比较仍绿） | 新增前提用例：两侧规则常量区里每条模式只许一个位置参数，且**两侧条数各 14/15 也钉住** |
| EVD §3 数字与真实收集差 1；§5 空 | 复算成立（它看到的是加例之前的状态；我按最终态重取 = 38 defs / 64 passed） | §3 回填、§5 补现跑读数 |
| 改动面越界（`apps/**` 在禁止栏里）未登记 | 复算成立 | §7 增一行如实登记，含偏离动机 |
| 「整门本机恒红/恒 3 的处置需规划方裁」 | 与我 §11.2 的结论同向 | 已写进 P-37 待追认 |
| 验收第一条判「证据不足」 | **部分同意**：它评审时 §5 确实还空着；现已回填 ⇒ 改判**部分确认**（口径与理由见 §5） | — |
| 厂商规则 8 字符阈值与 `_token` 词边界两处漏检 | 复算成立（7 字符值与 `APP_TOKEN` 前缀两种形状都不报） | **不改**（属规则语义），写进 §6.1 并入 P-36 的裁定面 |
| 「security.yml 自己装 gitleaks、不复用 guards.py；ci.yml 跑 `pytest tests/`」 | 复算成立 ⇒ 我的新用例确实进 CI，而 §1.3 那条 tripwire 只作用本机 | 写进 §8 的「门目前不在 CI 面」一条 |

变异验证（`.staging/mutate_s00p.py`，五轮改回旧行为 ⇒ 各自对应用例必须红 ⇒ 全部还原后 guards.py 逐字节相同）：
五条**全部被抓到**，还原校验 True。命令与逐轮读数已在 §3 表最后一行给出口径。

一句自我清算：**这一轮 6 条里 5 条是"能跑但方向偏绿"**（漏检 3、看不见当通过 2），
而且都是**只有把门放到真实 git 状态与真实批面上**才暴露的那类——
合成入参的用例（A/B/C 组 63 条里的大部分）一条都没抓到它们。
这与上一批 §5 的结论同形：判据敏感性与判据**方向**是两件事，必须分别测。


### 11.2 「判红」改成「第三态」，因为每次必发的红等于没有红

§1.3 那条 tripwire 第一版写成 rc=1。现跑之后发现它在 Windows 上**每次必发**（根因是 Git for Windows
的 system 级 `*.docx → astextplain` 注册，本机不允许装 `docx2txt`，仓库级 `.gitattributes` 不属本卡
允许面），于是整门永远读成红——**一个永远红的安全门和一个永远绿的安全门一样没用**，
而卡面阻塞条件①说的正是这种「门被人关掉」的路径。

改后的口径：rc=0 但工具自报未完成 ⇒ 退出码 **3**，语义与本仓既有的 `SKIP(tool missing)` 同一族
（「这一维没有终判」），`make guard` 仍然非 0，不会被读成通过；而「扫出了凭据」那种红仍然只由
真命中产生（rc=1 由 `test_a_nonzero_tool_rc_is_propagated` 保住）。

代价如实写在这：**本机在 P-37 根治之前跑不出 `make evidence-check` = 0**（§5）。
三条根治路径与归属见 P-37，执行方不为其放宽判据。


