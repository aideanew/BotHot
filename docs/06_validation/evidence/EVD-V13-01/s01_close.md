# STEP-01 余 2 项收口（规划方，2026-10-20，基线 bec5225）

## S1.3.2 第五轮：语义真源换成标准库（D-V8-05 选 A）
- dev 依赖加 `jsonschema==4.25.1`（`uv.lock` 同步，只增不改既有锁版本）。
- 新文件 `apps/api/tests/test_contract_jsonschema.py`，三层：
  1. 元校验：12 份文档（7 份带 `$schema` 的冻结稿 + 5 份产物）全过 Draft 2020-12 `check_schema`；反证：`maxLength: "512"` 被拒。
  2. 探针等价：19 对同名形状（含 `api.envelope` 根）在同一批探针上由 validator 判接受/拒绝；探针含两侧枚举、边界长度与数值、模式语料、类型代表值，以及两侧各自合成的合法对象和它的"缺必填 / 多键 / 换值"变体。反证：产物 `message.maxLength` 512→511、删掉 `requestId` 必填，两处都被分辨出来。
  3. 登记兜底：结论不同的形状必须有 `tightening` 或 `conflict` 登记；只有"接受集不变"四类登记的 ⇒ 红。
- 读数见 `s132_jsonschema_probe_readings.txt`：4 对结论不同，全部有改接受集的登记（identity:SessionClaims tightening；events:PushRetryState conflict；resources:ContentAsset / ShortLinkMap conflict = D-V8-06）。
- 旧比对器保留，文件头改写为"差异登记 + 覆盖率守卫"，不再单独决定语义。

## S1.2.2 最后一域：`api.envelope` 收编（D-V8-08 选 A）
- 唯一源 `apps/api/app/contracts/envelope.py`：`Envelope`（根即形状，`__contract_root__`）+ `PageStyleA` / `PageStyleB` / `PageTargetUnified`。
- 生成器 `scripts/gen_contracts.py` 支持"根即形状"：点名模型摊到产物根上、不再留在 `$defs`；产物 `packages/contracts/schemas/api.envelope.schema.json`。
- 冻结稿：`enumReference` → `x-enum-reference`；`x-pagination` 三个壳提升为 `definitions`（原文搬过去，`x-pagination` 只留裁决说明与查询参数说明）；`$id` 按 D-V8-03 统一为 `bothot://contracts/api.envelope/v1`，`errors.global` 对它的引用同步。
- 运行时证明：`core/response.py` 的 `success()/failure()` 产出的四种信封全部被产物根接受。

## 读数
- 契约两文件 217 passed；`gen_contracts --check` 11 项幂等一致。
- 本机真库全量 1902 passed / 5 skipped / 0 failed；ruff、mypy 全绿。新增用例均不连库，CI-Windows skip 阈值不变。

## 发现（交给后续卡，不在本卡改）
- identity `SessionClaims` 的 `extra="forbid"` 被登记成 `strictness`（文档定义为"接受集不变"），实际会拒收多余键 = 接受集收窄。本次能过只因同形状另有 `tightening` 登记。应改登记为 `tightening`。
- `date-time` 格式检查需要额外的 `rfc3339-validator` 包；未装时 validator 不判格式，两侧同样放过，结论不受影响但这一维没被覆盖。
