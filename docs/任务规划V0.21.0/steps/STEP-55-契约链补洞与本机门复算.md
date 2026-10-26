# STEP-55 契约链补洞与本机门复算（P-124、P-125、P-123 余项）

> 基线 main@92af50a（实际开工 head `e4a9a67`，差的是 STEP-54 的交付与收口两批，本卡允许面在其中零改动：
> `git log --oneline 92af50a..HEAD -- scripts/check_module_coverage.py apps/web/lib/api/spaces.ts` 零命中）
> 状态：✅ 三绿收口（交付批 `4a2c62b`，2026-10-26；CI 40320739120 / CI-Windows 40320739123 / Security 40320739138，均 attempt 1）｜版本 V0.21.0｜裁决 D-V21-12～14

| 字段 | 内容 |
|---|---|
| 1 归属 | 执行助手（S55.1 Agent-Web；S55.2 Agent-Guard；S55.3 Agent-Web） |
| 2 切片 | SL-SHAPE 收尾 + SL-DET |
| 3 来源 | P-124（摘掉 `satisfies` 两道门都看不见）、P-125（模块覆盖率门 @win 不可复算 + 附录 A 命令形式错）、P-123 余项（注释与僵尸文案） |
| 4 目标 | ① 任何一条 mock 路由的实际响应只要和它登记的契约不同形，vitest 就红——不靠手写 `satisfies` 是否还在；② 本机任何平台都能按附录 A 原样复算模块覆盖率门；③ 30101 不再被写成"线上码" |
| 5 输入 | `packages/contracts/schemas/{shapes,engine}.schema.json`（只读）、`apps/web/lib/api/mock-contract-map.ts`、`mock-routes.ts` 的分发入口；`scripts/check_module_coverage.py` 的 `_match`；`apps/web/lib/api/spaces.ts`、`types.ts` |
| 6 输出 | **S55.1** 新 `apps/web/tests/s55-mock-runtime-shape.spec.ts`：对对照表 22 条逐条用样例路径（路径参数填 `x1`，带 body 的给最小合法 body，`/auth/me` 先置登录态）走真实分发器拿到响应，再用**从 schema JSON 现读**的形状做递归核对：`required` 键全在、不出现 `properties` 外的键（`additionalProperties:false` 时）、`$ref`/数组元素/可空/`enum` 逐层递归、对象为空数组时跳过元素层但记一笔；核对器是测试文件内 ≤80 行的纯函数，**不手写任何键清单**，不加新依赖（D-V21-12）。自检：核对器对三份手造坏样本（多键/缺键/枚举外）必须报错。**S55.2** `_match` 改为两侧都把反斜杠换成斜杠、去掉前导 `./` 与 `/` 后比较"全等或以 `/`+key 结尾"；补纯函数单测（反斜杠相对形、正斜杠绝对形、多命中报错三例）；附录 A 第五节命令改为在仓库根跑并显式 `--json apps/api/coverage.json`（规划方已改，本卡只复核）。**S55.3** `spaces.ts` 注释改为"不存在/无权（30004）"；`ERROR_MESSAGES` 的 30101 保留但加注释"后端不产此码，仅为旧客户端兼容；线上未找到为 30004"（D-V21-14：发版前不删码，删除另排） |
| 7 验收 | ① 先红：摘掉任一条 `satisfies` 且同时让该条样例多一个键 ⇒ 现有门全绿、新用例红（原文入证）；再让一条样例缺一个必填键 ⇒ 新用例红 ② 22/22 条都真被分发并核对（用例里断言条数）③ S55.2 改前在 @win 复现 rc=2、改后 @win 与 @linux 都 rc=0 且 8 条各恰命中 1 个 ④ 全量 + 三绿 |
| 8 命令 | 同 STEP-52 第 8 格；后端门按改后的附录 A 第五节 |
| 9 证据 | `EVD-V21-55/` |
| 10 允许修改 | 第 6 格所列文件；`apps/api/tests/` 下新增 `test_module_coverage_match.py`（若已有同类测试文件则加在其中） |
| 11 禁止修改 | `packages/contracts/**`、`apps/api/app/**`、`mock-routes.ts` 的样例取值（核对器红就说明样例与契约不同形 ⇒ 登记 P 号交回，不改契约） |
| 12 依赖 | 52 ✅、54 ｜ Blocks：STEP-53 |
| 13 档位 | sonnet |
| 14 升级条件 | 某条路由的分发需要页面态或全局桩才能跑通、且 ≤10 行夹具搞不定 ⇒ 该条登记 P 号交回，其余照做 |
| 15 规模 | 中小，≈0.5 人日 |
| 16 熔断 | 同判据 2 次 FAIL ⇒ 停 |

## 三级任务
1. [x] **S55.1** 运行时形状门（从 schema 现读，不手写键清单）+ 核对器自检 + 先红两例 —— 交付出件见 `EVD-V21-55/s55_readings.md` §S55.1：`checkShape` 78 行（≤80 实测）、24 次分发零 errors、反证 A/B 两半 + 本轮追加的 C–H 共八条
2. [x] **S55.2** `_match` 路径归一 + 纯函数单测 + @win/@linux 双平台复算 —— 键形 8 条 0→1；另查出并修掉同一条门在本机的**第二个**复算障碍（cp936 末行 `✅`/`❌` 崩，rc=1 而判据全过），常驻用例 11→16；@linux 由 CI 判 ✅ 全部模块与全局达标
3. [x] **S55.3** 30101 注释纠真 —— `spaces.ts:48-51` 改 30004 并写依据；`types.ts:409-413` 在文案上方加四行说明，文案本体与组件四处并列判断一字未动（D-V21-14）
4. [x] **S55.4** 全量 + 三绿 + P-123/P-124/P-125 闭合 + 07 记录 —— 本机最终跑 13 步 12 步 0（唯一那条红是我 contracts typecheck 的调用形，按 CI 形复跑 0）：pytest **2471 passed / 6 skipped / 4 deselected**、覆盖率门按附录 A 原样不设编码变量判 0、vitest 53 文件 425 passed、mock e2e 31 passed；@ci 三绿同上；P-123/124/125 闭合行与新登记 **P-126**（STEP-46/47 复查提前跑出的孤儿 def 覆盖面，不阻塞 v1.1.3）见台账

## 为什么这样修（规划方说明）
P-124 的执行方建议是写 22 份键清单。我改成"直接读生成好的 schema"：schema 本来就是唯一源的产物、且有字节幂等门，再抄 22 份清单等于造第二个真源，迟早漂。核对器只需要懂本仓 schema 真实用到的几种写法（对象、数组、`$ref`、`anyOf` 可空、`enum`），80 行以内够用；遇到不认识的写法直接报错，不要静默放行——和生成器同一个纪律。
