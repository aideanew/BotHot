# EVD-V17-04：STEP-04 S4.5.1 复跑（V0.17.0 队列⑤ / V0.13.0 E-11）

- 日期：2026-10-20
- 基线：`main@03e1232`（STEP-31 记录提交；业务代码与交付提交 `5a2e471` 相同）
- 环境：Win10 + Git Bash；`apps/api/.venv` Python 3.12.10；`PYTHONUTF8=1`；
  隔离 PostgreSQL 16.4（`127.0.0.1:5547/bothot_test`，trust）；Redis/LangBot 未起。
- 本卡只复跑读数：不改业务代码、不新增用例、不动迁移。

## 1. P-2 复跑 = 0

```bash
cd apps/api && python -m pytest tests/test_manifest_asset_alignment.py \
  tests/test_manifest_state_machine.py -q -rs
```

读数：

```text
40 passed in 1.37s
```

构成：`test_manifest_asset_alignment.py` 15 条 + `test_manifest_state_machine.py` 25 条。
P-2 探针 `test_ready_article_is_not_re_enqueued`（`test_manifest_asset_alignment.py:636`）
在列并通过；本机带 DSN 实跑，40 条无 skip。

## 2. 单头与迁移往返

- `alembic heads` → `ab1006c1a (head)`，唯一头。
- 本机对隔离库做 `downgrade -1 → upgrade head`，**每拍都读形状**（不只看版本号）：

| 拍 | rc | `information_schema` 列 | `pg_indexes` 索引 |
|---|---:|---|---|
| `downgrade -1`（`ab1006c1a → ab1005w5b`） | 0 | `[]` | `[]` |
| `upgrade head`（`ab1005w5b → ab1006c1a`） | 0 | `[('article_manifests', 'article_key'), ('job_items', 'manifest_id')]` | `[('ix_job_items_manifest_id',), ('ix_manifest_source_article_key',)]` |

`alembic current` 终点：`ab1006c1a (head)`。

## 3. 契约门

```bash
apps/api/.venv/Scripts/python.exe -X utf8 scripts/gen_contracts.py --check
```

12 项产物全部 `幂等一致`，rc=0（6 个 TS dto + 6 个 schema JSON）。
输出中的 `alembic head 探测失败` 警告来自 `schema_guard` 在仓库根按相对路径
`alembic` 探测不到——不参与该生成器判定，命令 rc 仍为 0。

## 4. `@win` 全量同形状（E-11 的余量）

命令与 `.github/workflows/ci-windows.yml` 的 backend job 相同（不设
`AIDEANBOT_TEST_PG_DSN` / `DATABASE_URL`；连库用例按既有原因族 skip）：

```bash
cd apps/api
python -m pytest tests/ -q --no-header \
  -o faulthandler_timeout=120 --timeout=300 --timeout-method=thread \
  --junitxml=/d/tmp/s451_pytest_report_win.xml
```

读数：

```text
1453 passed, 571 skipped, 1 warning in 1045.40s (0:17:25)
RC=0
```

junit 汇总：`tests=2024 skipped=571 failures=0 errors=0`。

与 CI-Windows 的 backend 读数逐项相同（`1453 passed / 571 skipped / 0 failed`，
总数 2024），skip 计数与门禁 `baseline=571` 一致；连库用例按既有原因族 skip，
本机与 runner 同形状。

## 5. 三 CI

（待回填）

## 6. 边界

- 本卡 0 代码变更；`SKIP_BASELINE_WIN` 维持 STEP-31 的测量值 **571**，未新增用例。
- 未新增 P 项；P-50 / P-51 / P-52 未动。
