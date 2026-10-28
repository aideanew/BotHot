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
