# EVD-V24-70 · ERRATA（2026-10-29 自审补记）

> 本文件只登记两类事：**已推送文本里的错读数**，以及**本卡允许面之外、因此没改**的冲突。
> 已推送的 `readings.md` / P-160 行 / `07` 的 STEP-70 行**不回改**（D-V23-04「同号补登用新行不改旧行」），
> 正确读数以本文件为准。

## E-1（数值错，以本条为准）`offstate` 旧成员是 **97** 字符，不是 136

| 位置 | 现读 |
|---|---|
| `ux_states.before.json` 的 `NotificationBell.states["offstate"]` | **97** 字符（首 40 字：`⚠ MOCK_ENABLED 时 notifications.ts:103 直接…`） |
| 在库 `x-build-mode-notes["offstate"]` | **165** 字符 |
| `readings.md:16`、P-160 行 ⑤、`07` 的 STEP-70 行写的「136 字符的成员 / `offstate` 136→165」 | `136` 是**替换跨度**（含 `\n        "offstate": ` 等结构字节），**不是成员长度** |

正确长度对是 **97 → 165**。复算命令：

```bash
apps/api/.venv/Scripts/python.exe -X utf8 -c "
import json
b=json.load(open('docs/06_validation/evidence/EVD-V24-70/ux_states.before.json',encoding='utf-8'))
a=json.load(open('docs/任务规划V0.12.0/contracts/ux_states.schema.json',encoding='utf-8'))
bell=lambda d:[v for v in d['x-core-views'] if 'NotificationBell' in v['view']][0]
old=bell(b)['states']['offstate']; new=bell(a)['x-build-mode-notes']['offstate']
print(len(old),len(new), old in new)
"
# 现读输出：97 165 True
```

其余四处长度经复算**无误**：`note` 202→464、`rule5` 69→191、三处 `unauthenticated` 31/10/5→189/191/141；
在库 `sha256 = 2511aff55a10649f979398a7016f54bd9aad82de55eebcc9b8190d2d77d2954d`（与 `replay.json` 相同）。

## E-2（登记，不改）D-V23-02「冻结稿只读不改」与 D-V24-02 直接冲突

`docs/03_solution/decisions/decision-log.md:170` 的 D-V23-02 原话：

> 冻结稿 `docs/任务规划V0.12.0/contracts/ux_states.schema.json` **只读不改**

而 D-V24-02 由规划方下发本卡的五处替换。两条裁决并存，且**没有「取代」字样**（D-V23-15 取代 D-V23-… 时会明写）。
⇒ 本卡按 D-V24-02 执行（更新、且是本卡的作业指令）；D-V23-02 那句需要规划方补一句「由 D-V24-02 取代」或「只对 64/65 那一轮生效」。
裁决与台账的落笔权在规划方（D-V21-20），本卡只登记。

## E-3（登记，不改）`title` 仍是「核心界面**六态**契约」

现读 `title = "BotHot 核心界面六态契约（冻结稿 V0.7.0 / 基线 main@13acacc）"`，
而 `definitions.State.enum` 是 8 值、新 `note` 明确「8 值是全局词表」。
卡面 §5 只列五处替换，`title` **不在其中** ⇒ 按卡面 §13「出现 `03` §2 没覆盖到的第 6 处矛盾 ⇒ 停手交回」的口径，本卡不动它，交回规划方。
（同一文件 `description` 334 字符、`$id`、`$schema` 亦未动，见 `s70_checks.txt` §4 `title/description unchanged PASS`。）

## E-4（登记，不改）两处卡外副本仍是旧字节

| 路径 | 现读 | 性质 |
|---|---|---|
| `.staging/h983/docs/任务规划V0.12.0/contracts/ux_states.schema.json` | 仍写 `"x-required-for-every-core-view": true` | **未跟踪**的暂存副本（不在 git 索引里、不在卡面 §9 允许面内）；本卡不动，也不清理（可能是别的会话的在途工作） |
| `.workbuddy-ai/memory/2026-10-28.md:46` | 「`ux_states.schema.json` 四处互斥：`definitions.State` 8 值 + `x-required-for-every-core-view:true`」 | 另一会话/工具的笔记；若被后续会话当事实源会读到旧结论。不在允许面内，不代改 |

## E-5（核查结论：不是缺陷）新增语义没有机器守卫，但本卡也没这么宣称

`test_ux_states_contract.py` 四条的判据是「8 值同序」与「`note`/`x-required-for-every-core-view` 两个**键**仍在」，
不判「逐视图键集 ⊆ enum」。这符合卡面 §6 与 §10（禁止改任何测试文件）；该语义的守卫归 **STEP-68**
（`packages/contracts/src/ux/states.ts` 与测试面都在 68 的允许面内）。
`readings.md` §7 已写明「只改了冻结稿，没改任何产品实现」，未宣称语义已受门禁保护 ⇒ 无过称，不登记为缺陷。

## E-6（读数口径）@ci 读的是 `docs/**` 批，`backend` 仍会真跑那四条

`c46679f` 只动 `docs/**`，但 `ci.yml` 的 `backend` job 不按路径过滤 ⇒ 四条用例在 CI 上真执行。
CI 结论记在 `07` 的单独一行（本文件不预判）。

## E-7（第二轮自审：E-1～E-5 的四条订正，仍属只增不改）

独立校验方对 `8b695ce` 的八项判据全 PASS，但指出四处描述失准。以下为上文的**订正**，与上文冲突时以本节为准。

### E-7.1 归属订正：五处 ≠ 全归 D-V24-02

`decision-log.md:184` 的 D-V24-02 原话只含**四处**：「`x-required-for-every-core-view`→false、`note` 重写、`x-universal-rules[4]` 改逐视图口径、`offstate` 从 `states` 移到 `x-build-mode-notes`」；
三处 `unauthenticated`（本卡 S70.4）属 **D-V24-03**（`docs/任务规划V0.24.0/03-裁决与契约增量.md` §2.4）。
⇒ E-2 与 P-160 订正行里「D-V24-02 由规划方下发本卡的五处替换」应读作「**五处 = D-V24-02 四处 + D-V24-03 一处**」。
E-2 的结论（D-V23-02「只读不改」与两条 V24 裁决并存、无「取代」字样）**不变**：`grep -n 取代 decision-log.md` 全文件只在 **158 / 162 / 179 / 181** 四行命中（D-V21-17 行、D-V21-21 的「部分取代 D-V21-17」、D-V23-18、D-V23-20），D-V23-02（`:170`）与 D-V24-02（`:184`）两行均无此字样。

### E-7.2 E-5 对四条用例的描述失准

E-5 写「四条的判据是『8 值同序』与『两个键仍在』」——实际只有第 1、4 条判这两件。四条的真实判据（`apps/api/tests/test_ux_states_contract.py`）：

| # | 用例 | 判据 |
|---|---|---|
| 1 | `test_ux_states_literal_equals_frozen_draft_enum` | 活体 `UX_STATES` 与冻结稿 `enum` 逐值同序，且两侧计数 = 8 |
| 2 | `test_ux_domain_is_not_half_wired_into_the_generator` | `ux` 不在 `CONTRACT_SCHEMA_MODULES` / `CONTRACT_TS_DOMAINS`，且 `ux.schema.json` 产物不存在 |
| 3 | `test_index_ts_reexports_the_ux_state_type` | `index.ts` 导出 `UxState` |
| 4 | `test_frozen_draft_is_read_only_for_this_card` | 冻结稿 `State` 的 `note` 与 `x-required-for-every-core-view` 两个**键**仍在（只判存在，不判值） |

⇒ E-5 的**结论**（没有任何一条判「逐视图键集 ⊆ enum」、该守卫归 STEP-68）不变，变的只是「四条的判据是…」这一句概括。

### E-7.3 `136` 不追认「替换跨度」这个解释

E-1 说 136 是含结构字节的替换跨度——**无法复算**。按四种跨度定义实测：`8+12+97+1=118`、`21+97+1=119`、`…+“\”,\n”`=121、`…+CRLF`=122，**没有一种等于 136**。
⇒ 136 这个数字本身是错的，其来源不追认；正确读数只有 **97 → 165**。

### E-7.4 E-4 措辞收紧：`.staging/` 不是「未跟踪」，是「已忽略」

`.staging/` 被 `.gitignore:22` 整目录忽略（`git check-ignore` 命中、`git ls-files .staging` 0 命中）⇒ 它**永远不会**出现在 `git status` 里，比「未跟踪」更强。
结论不变（本卡不动它），只是 E-4 的「**未跟踪**的暂存副本」应读作「**被 .gitignore 忽略**的暂存副本（10-16 的旧字节，早于本卡）」。

### E-7.5 CI 面两条口径

- `e2e-real` 的 job 带 `continue-on-error: true`（`.github/workflows/ci.yml:547`）⇒ 它的 success **不是门禁**。`07` 的读数行只说「`e2e-real` 为 `completed/success`（不再被 `needs:` 连坐跳过）」，未称其为门禁，无过称。
- 第八个 check 的正式名是 `安全扫描（① pip-audit / ② pnpm audit / ③ trivy / ④ gitleaks）`；`07` 行简写为 `安全扫描`，属缩写。
