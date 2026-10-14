# STEP-13 可插拔引擎能力面收敛与需求对齐

| 字段 | 值 |
|---|---|
| 归属-切片 | S-M4 未纳管域补齐 |
| 归属-需求 | **REQ-F-003**（`product-requirements.md:86`）；分级 MUST（子集 M-3） |
| 归属-方案 | 本版 02 §5.2 遮蔽链、04 §4.13；裁决 **D-V3-03**（BLOCKING，默认「本轮不实接」） |
| 里程碑 | M4 |
| 档位 | **opus**　理由：本卡要界定「未实现需求 vs 技术债」的边界并冻结 `EngineCapability` 契约语义，属契约语义而非样板实现。**升级条件**：若 D-V3-03 被推翻为「实接某家」⇒ 升 `fable` 做范围终裁 |
| 规模 | 中（≈1 人日；单三级任务 <2h，S13.2.1 除外约 3h） |
| 依赖 | Depends on：STEP-01（契约唯一源已落）　Blocks：无（14/19 不依赖本卡） |
| 基线 | main@13acacc |
| 剩余原子任务 | 6（👤 1） |

## 目标（可验证的一句话）
`/engines` 与管理面对每个引擎能区分并如实显示三态之一——`ok` / `key_missing`（未配置密钥）/ `not_implemented`（骨架，16 处 `NotImplementedError`），且需求文本 REQ-F-003 的实现度与代码实况一致。

## 输入
- 文档：`01` F-78、`coverage §3`、`02` §6 B-3、`03` §2 D-V3-03
- 契约：`contracts/identity.schema.json#/x-permission-matrix`（管理面 rank=admin）
- 代码锚：`app/providers/engine_port.py`（`grep -c NotImplementedError` = **16**）、`app/api/v1/engines.py:121-122`、`engine_port.py:222-227`（`ENGINE_IMPLEMENTED` 仅 builtin:True）、`:253`（available 三条件）
- 前置状态：STEP-01 已合

## 输出（文件）
- `apps/api/app/api/v1/engines.py`（响应体增 `reason`/`implemented`）
- `apps/api/app/contracts/engine.py`（新，`EngineCapability`）
- `apps/api/tests/test_engines_capability.py`（新）
- `packages/contracts/src/**`（同提交重生成）
- `docs/02_requirements/product-requirements.md`（REQ-F-003 实现度小节）、`docs/04_engineering/backlog.md`（TECH-003b）
- `docs/06_validation/evidence/EVD-V3-13/`

## Execution Steps
1. [ ] 🔴 **S13.1.1** 先红：`test_engines_capability.py` 断言「未配置密钥」与「未实接骨架」两条 ForbiddenError 的 message 与 `reason` 字段**不同**；改前二者同形 ⇒ 红
2. [ ] 🛠 **S13.1.2** `engines.py` 响应体增 `reason ∈ {key_missing, not_implemented, ok}` 与 `implemented: bool`
   - S13.1.2.1 取值必须来自 `ENGINE_IMPLEMENTED`（`engine_port.py:222-227`），**禁止在路由层硬编码引擎名**
   - S13.1.2.2 不改 HTTP 状态（仍 403/10004），只改可读性 ⇒ 避免破坏 `errors.global` 契约
3. [ ] ✅ **S13.1.3** 基线读数：`grep -c NotImplementedError app/providers/engine_port.py` = 16 入 EVD，并注明「只降不升」
4. [ ] 📄 **S13.2.1** REQ-F-003 增「实现度」小节：builtin 可用；Ragflow 6 方法 / coze / dify / fastgpt / LangBot 建库 = 骨架，切换被拒且返回 10004
5. [ ] 📄 **S13.2.2** backlog 增 `TECH-003b`「实接需人裁决（依赖密钥、预算、网络出口 U-07）」
6. [ ] 🛠 **S13.3.1** `app/contracts/engine.py`：`EngineCapability`（Pydantic 唯一源，D-09）
   - S13.3.1.1 `python scripts/gen_contracts.py` 重生成且 `--check` rc=0（`ci.yml:97-105` 是阻断步）
7. [ ] 👤 **S13.3.2** 若发现需要任何 DDL ⇒ **立即停下上报**（本卡不占迁移号，03 §8 规则 ⑤）

## 验收标准
- [ ] `test_engines_capability.py` 两种失败态的 `reason` 断言绿，且改错任一处能红（变异反证）
- [ ] `grep -c NotImplementedError ...` 读数 = 16（未上升）
- [ ] REQ-F-003 文本与代码实况逐句一致（人工判断标准：按 §输入 的代码锚逐条比对，允许引用行号但不允许引用不存在的类/方法）
- [ ] `gen_contracts --check` rc=0；`ruff`/`mypy` 无新增错
- [ ] 全量连库 0 failed（依赖机）
- [ ] 无任何新迁移号被占用

## 验证命令
```bash
cd apps/api
grep -c NotImplementedError app/providers/engine_port.py                       # 期望 16
grep -n 'ENGINE_IMPLEMENTED' app/providers/engine_port.py app/api/v1/engines.py # 取值来源单一
.venv/bin/python -m pytest tests/test_engines_capability.py -q -rs
.venv/bin/python -m pytest tests/ -q -rs --junitxml=junit.xml                    # 0 failed
python ../../scripts/gen_contracts.py --check ; echo rc=$?
```

## 证据路径
`docs/06_validation/evidence/EVD-V3-13/`

## 允许修改
`app/api/v1/engines.py`、`app/contracts/engine.py`、`tests/test_engines_capability.py`、`packages/contracts/src/**`（生成）、`docs/02_requirements/product-requirements.md`、`docs/04_engineering/backlog.md`、EVD-V3-13
## 禁止修改
`app/providers/engine_port.py`（本卡只读；实接归 D-V3-03 被推翻后的新卡）、`app/models/**`、`alembic/**`、`apps/api/app/services/**`、`apps/web/**`（归 14b/15）

## 阻塞条件
1. 出现「需要建表才能表达 capability」⇒ 停，转 ADR + 迁移号裁决。
2. D-V3-03 被推翻为「实接」⇒ 本卡作废重写（实接是新切片，不在本卡扩张）。
3. 上游引擎无测试凭据 ⇒ 不得伪造响应样例，改判 `NOT_MEASURED` 并登记 U-07。
