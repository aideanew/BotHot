# EVD-V24-70 · STEP-70 `ux` 契约自洽化（P-150 + 契约四处互斥）

> 卡面：`docs/任务规划V0.24.0/steps/STEP-70-ux契约自洽化.md`
> 语义来源：`docs/任务规划V0.24.0/03-裁决与契约增量.md` §2（逐字新文本，唯一依据）
> 本卡是**纯契约卡**：改 1 个 JSON 文件（5 处替换）+ 1 行台账 + 本证据目录；
> `apps/**`、`packages/**`、`scripts/**`、`.github/**` 与任何测试文件**一个字节未动**。

## 1. 五处在字节上的落地

| 处 | 字段 | 旧 | 新 | 机器判据（`s70_checks.txt`） |
|---|---|---|---|---|
| S70.1 | `definitions.State["x-required-for-every-core-view"]` | `true` | `false` | §4 `S70.1 value is false PASS`；§5 `false_count=1` `true_count=0` |
| S70.2 | `definitions.State["note"]` 整串 | 202 字符 | 464 字符 | §4 `S70.2 note == 03 new (bytes) PASS len=464` |
| S70.3 | `x-universal-rules[4]` 整串 | 69 字符 | 191 字符 | §4 `S70.3 rule5 == 03 new (bytes) PASS len=191` |
| S70.4 | 三处 `unauthenticated`（`/spaces`、`/chat`、`/admin`） | 31 / 10 / 5 字符 | 189 / 191 / 141 字符 | §4 `S70.4a/b/c == 03 new (bytes) PASS` |
| S70.5 | `NotificationBell.states["offstate"]` → `x-build-mode-notes.offstate` | 136 字符的成员 | 165 字符的注记（对象内一键） | §4 `offstate out of states PASS`、`x-build-mode-notes.offstate == 03 new PASS`、`notes is an object, single key PASS` |

**新串不是手抄的**：脚本 `apply`/`replay` 都从 `03` §2 的**围栏块**里按小节抽取（`2.2` 的 `**新串**`、`2.3` 的 `**新串**`、`2.4` 的 (a)(b)(c) 的 `新：`、`2.5` 的 `**结构变化**` 之后那块），
再用「旧串（同样从 `03` 抽）必须与在库字节**逐字相等**」做前置断言，然后才替换。
⇒ 两侧任一处漂移，替换会在前置断言处红，而不是悄悄写入一份「看起来像」的文本。

**S70.5 的结构**（卡面 §5 步 5 只写了「剪切…放到新键下」，`03` §2.5 的落点是对象）：

```json
"states": { "loading": …, "empty": …, "success": …, "error": …, "degraded": … },
"x-build-mode-notes": { "offstate": "【构建态注记，不是 State 枚举值】…本键不在 definitions.State.enum 内，不参与逐视图键集比对（P-147）。" }
```

`x-build-mode-notes` 是**对象且只有一个键**（`s70_checks.txt` §4 第 9 条判的就是「不再是裸串」），
这样下一版若还要放别的构建态注记不必改形。新 `offstate` 串 = 前缀「【构建态注记…】」+ **旧串原文** + 后缀「本键不在…」，旧串仍是新串的子串（本机复算 `offstate_old_contained_in_new=True`）⇒ 产品侧与 vitest 里引用旧措辞的注释不需要跟着改语义。

## 2. 先红与改后（同一条探针，两个文件）

| 读数 | 改前（`ux_states.before.json`） | 改后（在库字节） |
|---|---|---|
| `x_required` | `True` | `False` |
| `note_len` | 202 | 464 |
| `universal_rule5_len` | 69 | 191 |
| 视图键集是否 ⊆ enum | `subset_fail_views=1`（`REQ-F-001` 多一个 `offstate`） | `subset_fail_views=0`（6/6） |
| `NotificationBell.states` | `['degraded','empty','error','loading','offstate','success']`（6） | `['degraded','empty','error','loading','success']`（5） |
| `x-build-mode-notes` | 不存在 | `['offstate']` |
| 三处 `unauthenticated` 长度 | 31 / 10 / 5 | 189 / 191 / 141 |

逐字输出见 `s70_checks.txt` §1（改前）与 §2（改后）。

**先红的性质与别卡不同**：`test_ux_states_contract.py` 在改前就是 4 passed（它判的是「八值同序」与「两个键仍在」，不判语义），
所以本卡的「红」不是 pytest 红，而是**契约自相矛盾本身**：`x-required=true` 与「一视图键集含 enum 外键」同时成立时，
任何逐视图断言都不可能同时满足两条。⇒ 判据写成 `s70_checks.txt` §1 的三行读数，而不是一个失败的用例。

## 3. 复现（从 before 拷贝重放，逐字节比对）

`s70_checks.txt` §3：

```
replay_bytes=9873 live_bytes=9873
replay_identical=True
replay_json_loadable=True
replay_rc=0
```

⇒ 一周后的人拿 `ux_states.before.json` + `03` §2 + 这组替换规则，能**逐字节**重建当前在库文件（`replay.json` 即重放产物，sha256 与在库相同）。

## 4. 与卡面 / 规划文本的四处出入（不代改，登记）

| # | 卡面或规划文本说 | 现读事实 | 本卡处置 |
|---|---|---|---|
| 1 | 卡面 §4 输出与 §9 写「P 表新增 **P-153**」 | P-153～P-159 已被占用（P-153～P-157 由规划方 `7c15264` 落，P-158/P-159 由批 1 三条闭合行落）；当前最大号 P-159 | **顺延到 P-160**（该号是规划方预留的空位，`07` §4 已说明「预留号等真有内容时再用」）。本行是内容，不是占位。P-161 仍空 |
| 2 | `decision-log.md` 的 D-V24-02 / D-V24-03、`docs/任务规划-索引.md:112` 都把「`ux` 契约自相矛盾」记作「**V0.23.0 P-147**」 | 台账 P-147 是 `e2e-real` 的两条红（admin ① AuthGate + `Stop stack` 端口残留），全文没有契约字样；契约自相矛盾在台账里**没有独立登记行** | 不代改裁决与索引（越出允许面）；在 P-160 的「条目」格里把「空号」这件事写死，交给规划方纠引用 |
| 3 | 卡面 §4 把 `EVD-V24-70/readings.md` 列在「修改」 | 本卡是证据目录首发，`readings.md` 是**新建** | 不改卡面措辞（纯文书笔误），在 P-160 与 `07` 里如实记 |
| 4 | 卡面 §6 末条「`git diff --stat` 只含第 4 节列出的文件」 | `git diff --stat` 只有契约 1 文件（+10 / −8）；证据目录是 untracked 新增；台账 1 行在提交时并入 | ✅（`s70_checks.txt` §7） |

**索引那一行仍未改**：`docs/任务规划-索引.md:112` 现读「**未解**，本版头号阻塞」，本卡允许面（§9）只有契约 / 本证据目录 / 台账 P 行三处 ⇒ 不动，已在 P-160 的「归属卡」格写明由规划方改判。

## 5. 不改面（逐条机械核对）

| 面 | 判据 | 读数 |
|---|---|---|
| `definitions.State.enum` | 8 值、顺序与改前逐值相同 | `enum unchanged (8, same order) PASS`；§8 `enum_same=True` |
| `State` 的两个注释键 | 键仍在 | `State keeps both keys PASS` |
| 其余 5 条 `x-universal-rules` | 逐字节相同 | `other 5 rules byte-identical PASS`；§8 `rules_other5_same=True` |
| 其余视图的态文案 | 除 `unauthenticated` 与 `NotificationBell` 外逐字节相同 | §8 五条 `states_minus_unauth_same=True` |
| `NotificationBell` 的变更面 | 只少 `offstate` 一个键、`x-build-mode-notes` 是唯一新增 | §8 `states_diff_removed=['offstate'] states_diff_added=[]` |
| 顶层键序 / `title` / `description` / 视图顺序 | 不变 | `top-level key order unchanged`、`title/description unchanged`、`view order unchanged` 三条 PASS |
| 文件编码形 | UTF-8 无 BOM、无 CRLF、以换行结尾 | `no BOM` / `no CRLF introduced` / `ends with newline` 三条 PASS |
| 测试文件 | 未动 | `git status --porcelain` 只有契约 + 本目录（§7） |

## 6. 下游：`/chat` 仍 5 键（STEP-60 的前提没被我改掉）

`03` §2.2 的新 `note` 自述「现读 6 个视图分别为 7/5/5/6/5/2 个键」，改后**实读逐格相同**（`view key counts == note 7/5/5/6/5/2 PASS`）：
`/spaces` 7、`/hot` 5、`/chat` 5、`/admin` 6、`NotificationBell` 5、`/onboarding` 2。
⇒ `V0.25.0/04` 的 `N-2`（不新增 `initial` / `forbidden` 态、`/chat` 仍 5 键）在本卡之后仍成立。

## 7. 局限与未做

| 项 | 说明 |
|---|---|
| 只改了冻结稿，没改任何**产品实现** | `apps/web/components/NotificationBell.tsx:239` 与 `apps/web/tests/notification-offstate.spec.tsx:5` 仍以注释形式引用旧 `offstate` 措辞；新串把旧串整句包含在内（§1 末），语义未变 ⇒ 不在本卡动 |
| 历史版本的冻结稿未动 | `docs/任务规划V0.7.0` / `V0.9.0` / `V0.11.0` 的 `ux_states.schema.json` 仍写旧规则；按 D-V10-06 冻结稿恒定，只改「当前被引用的那份」（V0.12.0） |
| `x-universal-rules` 的其余五条**未逐条对实现复核** | 这是 P-156 的既有自限，本卡只按 D-V24-02 改第 5 条，不据此宣称「契约已全自洽」 |
| 未跑全量回归 | 用户 2026-10-28 口径「拒绝全量回归/门禁」；本卡只跑 `test_ux_states_contract.py`（4 passed）与最可能被牵连的 `test_collection_contract.py`（219 passed） |
| @ci 读数 | 本文件写于推送前；CI 结论在后续提交回填（本卡改的是 `docs/**`，CI 的 `backend` job 会真跑这 4 条） |

## 8. 证据文件清单

| 文件 | 作用 | sha256 |
|---|---|---|
| `ux_states.before.json` | 改前原文件（先红臂 + 复现输入） | `818fa1c807e2e736a2beca6b4aecd94ee93ceae14c1aa87e2b2fd87a6ac484bc` |
| `replay.json` | 从 before 重放得到的产物；应与在库字节相同 | `2511aff55a10649f979398a7016f54bd9aad82de55eebcc9b8190d2d77d2954d` |
| `before_after.json` | 7 条（5 处，S70.4 拆成 a/b/c）的 old/new 原文 + 两侧 sha256 | `c508d1010cf9f79a7f3ea6b31e40a7949ea0b6ebb48e7a0719caa483bbb1b986` |
| `s70_checks.txt` | §0 基线 / §1 先红 / §2 改后 / §3 复现 / §4 25 条校验 / §5 grep / §6 pytest / §7 变更面 / §8 不改面 | `726ea5e3699cd2d6eb018ce6b421a38a0660c6c17c01b95cb79f477c5c22b2ed` |
| `readings.md` | 本文件 | — |

在库契约 `sha256 = 2511aff55a10649f979398a7016f54bd9aad82de55eebcc9b8190d2d77d2954d`（与 `replay.json` 相同）。
