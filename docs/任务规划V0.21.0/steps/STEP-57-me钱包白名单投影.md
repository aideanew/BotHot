# STEP-57 `/auth/me` 钱包白名单投影（P-121）

> 基线 main@97cc469（97c929e 之后规划方只推了一个提交 97cc469，全在 docs/ 下 ⇒ 本卡允许面在其中零改动）｜状态：✅ 已收口（2026-10-27，交付 685e3f8 三绿 attempt 1；**S57.3 契约封闭那一半按规划方裁定（P-129 出路③）不落地、另开卡**；收口批自指不抄自己的 sha）｜裁决 D-V21-17（取代 D-V21-09），第 3 步按 D-V21-20 之后的 P-129 裁定改道

| 字段 | 内容 |
|---|---|
| 1 归属 | 执行助手 Agent-API |
| 2 来源 | P-121：`services/auth/service.py:259` 把主平台钱包对象原样透传，主平台加任何字段都会直接出现在我们的接口里（含可能不该外露的字段），契约只能开放 |
| 3 目标 | 后端只吐已知五个键；契约 `MeWallet` 改为封闭对象（与其他 29 个 def 一致） |
| 4 输出 | **S57.1** 先红：新用例让桩主平台返回钱包多带一个键（如 `internalNote`）⇒ 断言响应里不出现该键（改前红）。**S57.2** 在 service 里加纯函数 `_project_wallet(raw) -> dict`：只取 `balanceYuan`、`currency`、`heldYuan`、`availableYuan`、`available`；**上游没给的可选键保持缺席，不补 0**；`balanceYuan`/`currency` 缺失时按现有降级形处理（`{balanceYuan:0, currency:"CNY", available:false}`），不抛 500。上游多出的键名（只记键名，不记值）以 debug 级别记一次。**S57.3** `shapes.py` 的 `MeWallet` 改继承 `_Closed`，删掉 `extra="allow"` 与相关注释；跑 `gen_contracts.py` 重新生成 schema/TS 并 `--check` 幂等；前端若因此 tsc 红，只改类型/样例不改契约 |
| 5 验收 | ① 先红原文入证 ② 纯函数单测四例：全键、缺可选键、多余键、缺必填键 ③ `extra=forbid` 反证：契约测试对多余键红——**本卡未执行这一条**：把它落地要与冻结稿 `docs/任务规划V0.12.0/contracts/shapes.schema.json` 那两行声明同步，而那份稿只有规划方能落笔（D-V21-20）；规划方 2026-10-27 在 P-129 三条出路里选定出路③，本卡只发投影那一半，反证随封闭一起转入后续卡（判据文字本身不回改，这一句是收口批代录裁定） ④ s55 运行时形状门、s52 覆盖门、mock e2e 仍绿 ⑤ 全量 + 三绿 |
| 6 允许修改 | `apps/api/app/services/auth/service.py`、`apps/api/app/contracts/shapes.py` 中 `MeWallet` 一个类、`gen_contracts.py` 生成的产物、`apps/api/tests/**`、`apps/web/**` 的类型与样例（仅当 tsc 要求） |
| 7 禁止修改 | 其余契约 def、其他 service、迁移 |
| 8 规模/档位 | ≈0.4 人日｜sonnet |
| 9 熔断 | 同判据 2 次 FAIL ⇒ 停；若发现前端真的读了五键之外的钱包字段 ⇒ 停下交回 |
