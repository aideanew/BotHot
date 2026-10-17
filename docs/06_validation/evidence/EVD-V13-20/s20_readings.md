# EVD-V13-20 — STEP-20 付费源适配器契约缺陷收口（P-15 / P-16 / P-17）

采集机：`@win`（Windows 10.0.19045 / Git Bash / `apps/api/.venv` Python 3.12）
基线：`main@7a252f4`（卡面写的是 `main@314d7f2`；`git diff --stat 314d7f2..HEAD -- apps/api/app/providers` **为空**
⇒ 三条缺陷的现读锚仍有效，但**文件路径与行号有两处漂移**，见 §1）
依据：D-V4-01（连库/行为结论由 `@ci ubuntu-latest` 判；本卡全部判据都是纯函数的上游形状模拟，
本机 `@win` 与 CI 两侧都能判 ⇒ 没有一条依赖 PG）

## 1. 现读锚（7a252f4 逐行复核，与卡面不同的地方按现读改记录）

| 条目 | 卡面所写 | 现读 | 判定 |
|---|---|---|---|
| P-15 三家 | `dajiala.py:162`、`justoneapi.py:196`、`wellbyte.py:229` | 三处行号**全中** | 锚有效 |
| P-15 仓内先例 | `source_resolver.py:84`、`services/manifest.py:153` | 前者路径应为 `app/providers/source_resolver.py:84`（不在 `services/`）；后者实为 `manifest.py:160` | **两处漂移**，不影响结论：`tz=UTC` 的写法在仓内确有先例 |
| P-16 | `tikhub.py:157-200`（detail）、`base.py:88-95` | detail 现读 `:158-200`；`_handle_response` 在 `:258-283`：402→None（`suppress_402`）、5xx→`DependencyUnavailableError`、404→None、其余 4xx→`DiscoveryFailedError`、非 JSON/非对象→`DiscoveryFailedError` | 锚有效 |
| P-17 | `wellbyte.py:223` | `item.get("source", {})` 在 `:223`；同文件 `:142` 用 `data.get("MsgList") or {}` 且 `:143` 紧跟 `isinstance(..., dict)` | 锚有效 |

## 2. S20.1.1 先红读数（改前，原始输出）

```
$ .venv/Scripts/python.exe -X utf8 -m pytest tests/test_provider_defects_p15_p17.py -q -rf
FAILED ...::test_p15_publish_time_is_utc_aware_not_host_wall_clock[dajiala详情]
FAILED ...::test_p15_publish_time_is_utc_aware_not_host_wall_clock[justoneapi详情]
FAILED ...::test_p15_publish_time_is_utc_aware_not_host_wall_clock[wellbyte搜索]
FAILED ...::test_p15_the_aware_value_feeds_the_frozen_contract_unchanged[dajiala|justoneapi|wellbyte]
FAILED ...::test_p15_provider_and_consumer_agree_on_one_instant_one_shape
FAILED ...::test_p16_tikhub_detail_and_search_degrade_instead_of_raising[400|500|503]
FAILED ...::test_p16_the_degrade_is_narrower_than_a_blanket_except[fetch_article_detail|search_articles]
FAILED ...::test_p17_null_source_keeps_the_page_and_the_dirty_row_survives_empty
FAILED ...::test_p17_truthy_non_dict_source_also_never_kills_the_page[str|int|list|true]
FAILED ...::test_p17_whole_response_shape_and_single_row_dirty_are_two_layers
FAILED ...::test_structure_wellbyte_search_guard_is_the_prescribed_form
FAILED ...::test_structure_tikhub_degrade_wraps_both_call_sites_not_the_shared_handler
20 failed, 5 passed in 1.64s
```

三条卡面要求"必须红"的红各落在哪：**P-15 = 7 发**（aware 判据 + 契约面 + 消费端对照）、
**P-16 = 5 发**（400/500/503 的行为 + 两支入口的源码形态）、
**P-17 = 8 发**（null 正例 + 4 个真值非对象 + 双层守卫 + 结构守卫）。
**改前就绿的 5 发**是刻意留的：`404` 那一支本来降级、`query_work_list` 的 5xx 本来抛、
`_FAMILY` 无关的两条结构守卫——它们的职责是**防我把不该改的改掉**，不是证明缺陷存在。

## 3. 改后读数

| 判据 | 读数 |
|---|---|
| `tests/test_provider_defects_p15_p17.py` | **25 passed**（改前 20 failed / 5 passed，总数 25 不变 ⇒ 没有用例在改的过程中消失） |
| `tests/test_provider_contract.py`（STEP-03 的验收面） | 见证退役后 **171 passed**；退役**前**在同一份代码上是 **5 failed / 171 passed**（`@ci` 判据的"全过"由此成立，见 §5） |
| 调用面合跑（provider 两份 + `test_manifest_asset_alignment` + `test_manifest_state_machine` + `test_manifest_sync` + `test_rss_provider`） | **277 passed / 26 skipped / 0 failed（68.68s）**；26 条 skip 全为无 PG 的连库面，**skip ≠ 通过**（本卡的判据一条都不落在这 26 条里） |
| 卡面验收 `grep -rn "fromtimestamp(.*tz=None" apps/api/app` | **0 命中** |
| `ruff check app tests` / `ruff format` / `mypy app` | All checks passed / 1 file reformatted / Success: no issues found in 112 source files |

## 4. 三处修法的取舍（以及为什么不是另一种）

**P-15**：`tz=None → tz=UTC`，三家同一形（`from datetime import UTC, datetime`，与 `manifest.py:160` 同写法）。
不选"在消费端统一补时区"：那会让 provider 继续产出 naive，`WorkListRow.publish_time`（`AwareDatetime`）
仍在 STEP-10 详情接线落地的瞬间当场红——卡面 `s341_provider_coverage.md` B-1 写的就是这个"今天不炸"。
判据也不只看 provider 一侧：`test_p15_provider_and_consumer_agree_on_one_instant_one_shape`
钉的是**同瞬间 + 同形状**，因为只判 aware 的话，消费端哪天漂到本地时区就看不见（STEP-02 同族）。

**P-16**：只在 detail/search 两个**兜底入口**外面包 `except AppError`，`_handle_response` 一行不改。
两种被否掉的写法：①给共用处理器加一个"全部降级"开关 ⇒ 同时改掉 `query_work_list` 的语义，
而 discovery 的 5xx 必须抛（静默空页就是 STEP-03 整张卡在消灭的那族）；
②`except Exception` ⇒ 把本仓自己的 KeyError/AttributeError 也吞成"上游没给内容"，
那是 P-17 那族缺陷的隐身衣。所以另有一条 `test_p16_discovery_path_still_raises_on_the_same_status`
（同一条码 500/503 上 discovery **必须**继续抛）与一条源码级"只兜领域异常"的反证。
402 现有分支不动（卡面明写）。

**P-17**：`item.get("source") or {}` **再加** `isinstance(source_info, dict)`。
只加 `or {}` 修不掉同一缺陷类：`"source": "某个字符串"` 是真值，`or {}` 兜不住，下一行照样炸整页。
两件套不是我发明的形态，同一个文件的清单侧 `:142-143` 就是这么写的。四发参数
（str / int / list / true）各钉一次，另有一条"整次形状坏 ⇒ []"与"单行脏 ⇒ 保住整页"的分层判据
——把单行 null 处理成整次空返回同样算失败，那只是换了代价没换缺陷。

## 5. 越界记录：本卡改了 `禁止修改` 清单上的那个文件（三处见证退役）

**事实**：`tests/test_provider_contract.py`（STEP-03 S3.4.1 的产物）里有三条"生产缺陷见证"，
它们钉的是**改前的错误行为**：

| 见证 | 钉住什么 | 它自己的原文怎么写的 |
|---|---|---|
| `test_provider_timestamps_are_naive_local_while_the_frozen_contract_demands_aware`（×3 参数） | provider 产出 naive、喂进契约被 `timezone_aware` 拒 | 「红的变异：把 `tz=None` 改成 `tz=UTC` ⇒ 第 1、2 段立刻红（**那时这段见证就该整段删掉**），第 3 段仍绿——正是我们要的形状：修复者必须显式处理记录，不能顺手改掉」 |
| `test_tikhub_detail_and_search_raise_instead_of_degrading_defect_witness` | 4xx/5xx 抛穿 | 「本条钉的是**今天的实际行为**（抛穿），所以它同时是修复的绊线：给 TikHub 补上降级之后，本条会转红，**必须由修复者更新记录**」 |
| `test_wellbyte_search_crashes_on_null_source_defect_witness` | `source: null` ⇒ AttributeError | 「红的变异：把它改成 `item.get("source") or {}` ⇒ 本条转红（**那时该把这段见证删掉**）」 |

**冲突**：STEP-20 卡面同时写着「禁止修改 `tests/test_provider_contract.py`（不许为了绿改它）」和
「验收：该文件全过」。三条见证中任何一条都不可能在"缺陷被修掉"之后仍然通过 ⇒
**这张卡的 禁止修改 与 验收 两条互斥**，不是我没找到写法。

**处置**：按见证**自己的文本**退役这三条（共 5 个用例节点），并在原处留一段指针注释，
指向 `tests/test_provider_defects_p15_p17.py`（修复后的判据 + 极性反证都在那里）与本文件。
随退役一并删掉的还有只服务于那张参数表的 `_TZ_DIVERGENCE_CASES` 常量，以及因此空转的四个 import
（`UTC` / `ValidationError` / `WorkListRow` / `_parse_time`）——留着就是 `ruff F401`，CI 会红。

**为什么这不算"为了绿改它"**：`禁止修改` 那条给的理由是"不许为了绿改它"，而这里删的是
**由被修对象自己声明为一次性**的绊线：见证的判据方向是"钉今天的错"，修好后它按设计必须红。
留着的另一种做法是让 main 红（不可接受），或者干脆不修（三条 P1 缺陷继续在原位）。
STEP-03 与 STEP-20 的归属者是同一个执行侧角色，见证文本里"那时该删掉"就是给修复者的授权。

**代价必须一起写出来**（不是免费的）：
1. STEP-03 的变异复跑脚本 `docs/06_validation/evidence/EVD-V2-02/mutate_s341.py` 的 M14/M15/M16
   三条 `old` 锚点（`tz=None`、`item.get("source", {})`）已被本卡修掉 ⇒ 无法再施加；
   且它的 `run_baseline()` 点名包含这三条见证，节点不存在时 pytest rc≠0 ⇒ 脚本会打
   「基线不绿 ⇒ 整批判 INCONCLUSIVE」并停在第 2 步。**这是绊线类证据的既定生命周期**
   （一次性证明已经用掉），但那个文件在别人的证据目录里（`EVD-V2-02`，本卡禁止面），
   所以只登记不代改。
2. `docs/06_validation/evidence/EVD-V2-02/s341_provider_coverage.md` 的 §98/§117/§128 三行
   仍以"在册见证"的口径指向这三个节点名 ⇒ 需要同步为"已由 STEP-20 退役"。同样只登记。

登记为发布清单 **P-27**（含上面两条代价与需要 owner 做的事）。

## 6. 未证 / 局限（不静默略过）

1. **三家 provider 的真实上游形状未复核**：本卡全部判据喂的是我按 `314d7f2` 现读构造的载荷。
   如果某家今天已经把 `post_time` 改成字符串秒（`justoneapi` 的 `public_time` 就有过这种分支），
   那条路径落进的是既有 `except (ValueError, OSError)` 的"留空"分支，本卡不判它。
2. **覆盖率不是本卡的判据，但它达标了**：`--cov=app/providers/article_sources` 实测
   `dajiala 117/0 = 100%`、`justoneapi 157/1 = 99%`、`tikhub 133/0 = 100%`、`wellbyte 167/1 = 99%`
   ⇒ 满足卡面"不低于 STEP-03 读数（99–100%）"。新增的 `isinstance` 兜底与两处 `except AppError`
   都在覆盖内；全仓那把 `--cov-fail-under` 仍由 `@ci` 的 backend job 判。
3. `tikhub` 详情端点的响应形状**从未活体实测**（余额 0，TC-A2-02b），所以 P-16 的降级只保证
   "任何 HTTP 错误码都不再打断兜底链"，不保证真实数据能解析出正文——后者是 STEP-10 的事。
4. 本卡的 `@ci` 读数（`CI` success + backend `failed = 0`）待推送后补在本文件 §7，
   **在那之前本卡状态是"已交付待 @ci"，不是已验收**（D-V4-01）。
