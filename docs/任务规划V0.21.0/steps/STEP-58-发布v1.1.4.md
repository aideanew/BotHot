# STEP-58 发布 v1.1.4

> 状态：✅ 已发布并收口（注释 tag `v1.1.4` ＝ 标签对象 `dd71da7` 指向发布批 `c682acd`，该 head 三绿均 attempt 1：
> CI 40465549229 / CI-Windows 40465549197 / Security 40465549190；Release 页 GET → HTTP 200、id 425152771；
> 既有标签推前后逐字未动——远端 5→6 枚，本地 `show-ref` 7→8 行，两枚从未推送的 `local-recovery-*` 仍在本地，
> 这正是没有 `--tags` 全推的实证）｜执行助手 Agent-Doc｜依赖 56、57 收口且同一 head 三绿（前置读数见
> `EVD-V21-58/s58_0_preopen_ci_readings.txt`）｜裁决 D-V21-18

流程、证据形状、禁止项与 `STEP-53-发布v1.1.3.md` 完全相同，只替换：版本号 v1.1.4；S58.1 独立复查对象改为 STEP-56、57（任一 FAIL 或 UNKNOWN 不发版、交回）；CHANGELOG 区间为 v1.1.3..HEAD。只打并推送 `v1.1.4` 一个注释标签，不用 `--tags`，既有七个 tag 逐字不动；补 Release 页并 GET 得 200。证据 `EVD-V21-58/`。
