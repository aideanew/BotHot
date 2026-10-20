# STEP-30 S30.2 复查 STEP-01 — 判定：PASS

- 复查对象：`docs/任务规划V0.13.0/steps/STEP-01-采集域契约冻结与契约收编.md`（交付 25088c4；证据 `EVD-V13-01/`）
- 复查基线：main@482769a
- 环境：本机 PG16 @ `127.0.0.1:5547/bothot_test`；Windows + Git Bash

## 逐条验收

| # | 卡面验收标准 | 判定 | 证据 |
|---|---|---|---|
| 1 | `tests/test_contract_jsonschema.py` 与 `tests/test_collection_contract.py` 全绿 | PASS | S30.4 后复跑：`225 passed in 4.03s`（RC=0） |
| 2 | 自己改一处产物确认探针等价用例变红后还原 | PASS | 产物 `packages/contracts/schemas/api.envelope.schema.json` 的 `properties.message.maxLength` 512→511 ⇒ 对应用例红，输出见下；已还原（blob MATCH） |
| 3 | `gen_contracts --check` rc=0 | PASS | 五份 schema 幂等一致，RC=0 |
| 4 | 全量真库 `failed = 0` | PASS | `s30_full_readings.txt` |
| 5 | S30.4：`SessionClaims` 的 `identity-extra-forbid` 登记由 `strictness` 改为 `tightening`；契约两文件全绿；`gen_contracts --check` rc=0 | PASS | 1 行 diff 见下；`225 passed`；RC=0 |

## 产物改坏反证（S30.2 第 2 条）

改坏：`api.envelope.schema.json` 的 `properties.message.maxLength` 由 512 改为 511。

```text
FAILED tests/test_contract_jsonschema.py::test_draft_and_generated_agree_on_every_probe[api.envelope:<root>]
E   AssertionError: api.envelope:<root> 稿与产物接受集不同（1 条探针），而登记种类=['documentation', 'structural']
E   （只有 tightening / conflict 才允许接受集不同）。样例：{"code": 0, "message": "aaaaaaaa…"} 稿=True 产物=False
1 failed in 0.53s
```

还原后 `git hash-object` = `git rev-parse HEAD:...` ⇒ MATCH。

## S30.4 P-48 更正

`apps/api/app/contracts/identity.py`：

```diff
         "SessionClaims",
         "additionalProperties",
-        "strictness",
+        "tightening",
         "identity-extra-forbid",
```

依据：`Divergence.kind` 的语义是（`apps/api/app/contracts/__init__.py:18-23`）

- `strictness` = 接受集不变，但多余字段被丢弃而非透传；
- `tightening` = 模型比 JSON Schema 严，接受集收窄。

`SessionClaims` 用 `extra="forbid"`，未知 claim 被直接拒绝 ⇒ 接受集收窄，原登记 `strictness` 与事实相反（P-48）。
比对器在"产物单方面新增约束"这一档显式接受 `tightening`（`apps/api/tests/test_collection_contract.py:937-952`），
且登记引用的 **D-V8-07** 仍在位，因此更正后两文件全绿、`gen_contracts --check` RC=0。

## 观察（不计 FAIL）

- 另一次改坏尝试：`collection.schema.json` 的 `ArticleManifest.content_hash.maxLength` 64→63，
  探针等价用例未变红；已还原（blob MATCH）。事实仅记录为"该有限探针语料未分辨此变异"，不据此判 FAIL：
  S30.2 的"改一处产物必须红"判据由上面的 envelope 用例满足；手改生成物仍被字节级漂移门
  `gen_contracts --check` 拦截。是否把该覆盖面登记为新缺陷由规划方裁决。
