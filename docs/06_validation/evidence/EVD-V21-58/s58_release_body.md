# BotHot v1.1.4（2026-10-27）

补丁 + 质量版：**契约 def 覆盖面补一道孤儿守卫**，**`GET /auth/me` 的钱包改成白名单投影**。
零数据库迁移、零新增对外 HTTP 端点；区间 `v1.1.3..HEAD` 共 8 个提交（含发布批自身）。

## 本版两处实打实的变化

- **`/auth/me` 不再外溢未声明的钱包键**（`apps/api/app/services/auth/service.py` 的纯函数 `_project_wallet`）：
  只吐 `balanceYuan` / `currency` / `heldYuan` / `availableYuan` / `available` 五个键；上游没给的可选键**保持缺席、
  不补 0**；必填键缺失或为 `null`、或整块不是字典 ⇒ 回既有降级形 `{balanceYuan:0, currency:"CNY", available:false}`
  且**不抛 500**；上游多出的键名以 debug 每次记一次、值一律不落日志。`/me` 三条分支（正常 / 主平台不可达 /
  QA fixture）的降级形现在同源。8 条常驻用例钉住（1 条走完整登录链的集成 + 7 条纯函数）。
- **契约 def 覆盖面孤儿守卫**（新 `apps/api/tests/test_contract_def_coverage.py`）：种子从两个反向核测试模块
  **现读**（shapes 取 `_check(<名>, <响应值>)` 调用点、引擎取带 `db_session` 用例里 `_errors(<常量>, data)` 的常量绑定），
  沿 `$ref` 求可达闭包，判 `全部 def − 可达集 == ∅`，红时点名孤儿；引擎域不再例外。同一条清单还判坏边
  （指向本域不存在的 def）、跨域 `$ref`、写错的种子名，坏边扫每一个 def。现读 21 种子 / 34 def / 孤儿 0 ⇒
  补的是会漏未来漂移的覆盖面，不是现存缺陷（闭合 P-126）。
- 顺带两处**契约链判据由弱变强**：引擎 TS 产物判据从"名字两侧各有一空白"的子串换成钉 `export interface`/
  `export type` 导出位本身的正则（配常驻反证）；冻结稿↔生成 schema 从"只有逐对探针、列表按名字集的交构造"
  升级为 `genOnly` 出现即红 + `draftOnly` 逐个必须指得出三条既有去处 + 探针列表与装饰器同串。

## 一条必须一起读的限定

契约里 `MeWallet` **仍是全 30 个 def 中唯一一个开放对象**（`additionalProperties: true`）——所以演示态样例多写
一个键、或前端 TS 类型那一层，都不会红。把它改封闭要与冻结稿 `docs/任务规划V0.12.0/contracts/shapes.schema.json`
那两行声明同步，而冻结稿只有规划方能落笔；规划方裁定本卡只发投影那一半（台账 P-129 出路③），
**P-121 记为部分闭合**，封闭那一半转入后续卡。另两处残留已登记：可选键被上游显式发成 `null` 时按"给了值"
原样带出；`data` 发成列表时 `/auth/me` 仍会 500（非本版引入，P-128）。

## 测试基线（发布批三绿 head）

CI `2496 passed / 6 skipped / 4 deselected`、skip 门禁 `6=6` 且 `pg_unreachable=0`、
`Total coverage` 落在 88.89–88.92（**这个数不可当精确判据**，同树/跨提交会抖 ±1 行）、模块覆盖率门
`✅ 全部模块与全局达标`、前端 `53 文件 / 425 passed`、演示态 e2e `31 passed`、
CI-Windows `1810 passed / 692 skipped` 且 `failed=0 total_skipped=692 baseline=692`。

## 发版依据与证据

STEP-58 卡（队列 56 → 57 → 58 末张，依据 D-V21-18）。发布门：对 STEP-56、STEP-57 的两份独立复查
**均为 PASS-with-nits，无 FAIL、无 UNKNOWN**。逐条判据、tag/Release 读数与标签前后对账见
`docs/06_validation/evidence/EVD-V21-58/`；变更明细见 `CHANGELOG.md` 的 `[v1.1.4]` 段。
