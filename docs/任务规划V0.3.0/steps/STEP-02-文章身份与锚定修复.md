---
id: STEP-02
title: 文章身份：canonical key + 锚定去 LIKE（P0-1 / P0-1b）
baseline: main@4afaedd
tier: sonnect
size: 中（约 1.5–2 人日）
---

# STEP-02：文章身份：canonical key + 锚定去 LIKE（P0-1 / P0-1b）

## 归属
- 所属切片：S2 可演示：同号两篇长链文章各自入库；库内多源时长链入库不崩溃
- 来源需求：M-01、M-02、REQ-F-004（短链映射）
- 来源方案：ADR-0011；01 §4；探针 P-3/P-4

## 目标
P-3 输出 `fetch_count=2 B.hitCache=False same_doc=False`、P-4 输出 `PROBE2 ok False`，并以常驻测试锁定。

## 输入
- ADR-0011（STEP-01.1.1）
- app/contracts/collection.py（ARTICLE_KEY_PATTERN）
- tests/fixtures/wechat_urls.py（STEP-00 已有 10 常量）
- kb.py:245/284/336-363/386/554-593
- 前置：STEP-00R 合入

## 输出（新增/修改的文件）
- apps/api/app/services/article_identity.py（新）
- apps/api/app/services/kb.py
- apps/api/app/repositories/asset.py（get_by_url_fragment 片段长度守卫）
- apps/api/tests/test_article_identity.py（新）
- apps/api/tests/test_kb_longlink_ingest.py（新）
- apps/api/tests/test_p0_asset_cache.py、test_idempotency_lock.py、test_d04_short_link.py（仅复刻旧键的断言）

## Execution Steps（三级原子任务 → 四级执行步骤）

标记：🔴 先红（失败测试/反证）｜🛠 实现｜✅ 验证｜📄 文档｜🗄 数据/迁移｜👤 人工/裁决。每个原子任务单独可验收。

### S2.1 共同部分（不依赖 D-V2-01）

#### S2.1.1 🔴

**交付**：`test_article_identity.py`：`parse_wechat_url` 对 LONG_A/LONG_B 解析出相同 biz、不同 mid；`__biz` URL 编码（%3D%3D）可解；LONG_A_TRACKING 与 LONG_A 解析出同 (biz,mid,idx)；SHORT_1 得 token（=SHORT_TOKEN_1）；SHORT_WITH_FAKE_BIZ_PARAM 仍解析出 biz（保持 test_p0_asset_cache 现有语义，`__biz` 优先于 `biz`）；MALFORMED_LONG 的 mid 为空；OFFSITE 返回 host≠微信

**执行步骤**：
1. [x] 只写测试，模块不存在 ⇒ ImportError 即红（本机实测见 `EVD-V2-02/README.md` §3：
   「改前红」现已做成可重放命令，用 `sys.meta_path` 只拦该模块名，不删文件）

**验收命令**：
```bash
cd apps/api && uv run pytest tests/test_article_identity.py -q  # 改前红
```

#### S2.1.2 🛠

**交付**：`article_identity.py`：`WechatUrlParts(biz, mid, idx, sn, short_token, host)` + `parse_wechat_url(url)`；`idx` 缺省 '1'；纯函数、零 IO

**执行步骤**：
1. [x] 实现（S2.1.1/S2.1.2/S2.1.3 已交付，见文末执行记录；S2.1.4 起未做）
2. [x] S2.1.1 转绿（本机真实 pytest `14 passed`，`--noconftest`，见 EVD-V2-02 §2 通道 A）
3. [x] 覆盖率 100%（`sys.settrace` 语句覆盖 27/27；卡面 `--cov-fail-under=100` 本机不可复现 ⇒ J-1）

**验收命令**：
```bash
cd apps/api && uv run pytest tests/test_article_identity.py -q --cov=app.services.article_identity --cov-fail-under=100
```

#### S2.1.3 🔴🛠

**交付**：`kb._biz_from_url` 改为委托 `parse_wechat_url(url).biz`（同时识别 `__biz` 与 `biz`）；补测试

**执行步骤**：
1. [x] 先写断言 `_biz_from_url(LONG_A)!=''` 红（`out_s213.txt` A 段：`合计 PASS=2 FAIL=9`，rc=1）
2. [x] 改实现转绿（`out_s213.txt` B 段：`合计 PASS=11 FAIL=0`，rc=0；C 段三条反证通道全过）

**验收命令**：
```bash
cd apps/api && uv run pytest tests/test_article_identity.py -q -k biz
```
> 命令缺陷（登记于执行记录）：本步交付物是 `tests/test_kb_longlink_ingest.py`，卡面命令却指向
> `test_article_identity.py`——按字面跑得到 `5 passed, 9 deselected`（`out_s213.txt` E 段），
> 但**一条都不覆盖 kb 委托**。应改为
> `uv run pytest tests/test_kb_longlink_ingest.py tests/test_article_identity.py -q -k biz`；
> 本步交付物的实跑受依赖限制（`kb.py:22-25` 模块级 import structlog/sqlalchemy，本机皆无，
> 收集期即 `ModuleNotFoundError`，见 `out_s213.txt` D 段）⇒ 本机侧由 A/B/C 三段等价证明承担，
> 有依赖环境侧的真实执行登记为 J-5。

#### S2.1.4 🔴🛠

**交付**：`kb._find_source_by_anchor`：删除 `Source.url.like('%{key}%')` 兜底；查询全部 `.limit(1)`；P-4 转正为 `test_kb_longlink_ingest.py::test_multi_source_no_crash`

**执行步骤**：
1. [ ] 复制探针为常驻用例（改前红：MultipleResultsFound）
2. [ ] 删 LIKE、加 limit
3. [ ] 转绿

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests/test_kb_longlink_ingest.py::test_multi_source_no_crash -q
```

#### S2.1.5 🛠

**交付**：`get_by_url_fragment` 加守卫：片段长度 < 8 直接返回 None 并记 WARNING（禁止 's' 这类单字符命中）

**执行步骤**：
1. [ ] 加守卫 + 单测

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests -q -k url_fragment
```

### S2.2 规范键（依赖 ADR-0011）

#### S2.2.1 🔴

**交付**：`test_article_identity.py` 增：`canonical_article_key` 对 LONG_A≠LONG_B、LONG_A==LONG_A_TRACKING、SHORT_1 走短链分支、OFFSITE 走 hash 分支、全部匹配 `ARTICLE_KEY_PATTERN`、任何输入都 ≠ 's'

**执行步骤**：
1. [ ] 写断言（改前红）

**验收命令**：
```bash
cd apps/api && uv run pytest tests/test_article_identity.py -q -k canonical
```

#### S2.2.2 🛠

**交付**：实现 `canonical_article_key(url)`（格式按 ADR-0011）

**执行步骤**：
1. [ ] 实现
2. [ ] 转绿

**验收命令**：
```bash
cd apps/api && uv run pytest tests/test_article_identity.py -q
```

#### S2.2.3 🛠

**交付**：`kb._article_key` 委托 `canonical_article_key`；`ShortLinkMap(article_key=…)`（kb.py:386）写规范键；缓存查询（:245/:284）用规范键

**执行步骤**：
1. [ ] 改 3 处调用点
2. [ ] P-3 转正 `test_kb_longlink_ingest.py::test_two_distinct_long_links`（期望 fetch_count=2）

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests/test_kb_longlink_ingest.py -q
```

#### S2.2.4 🛠

**交付**：历史键兼容：缓存未命中规范键时，仅对短链再用旧裸 token 查一次（只读兼容，命中后不改写；改写由 STEP-07）

**执行步骤**：
1. [ ] 实现 + 单测：预置旧键资产 ⇒ 短链二次入库仍 0 抓取

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests/test_d04_short_link.py -q
```

### S2.3 回归

#### S2.3.1 🛠

**交付**：更新复刻旧键算法的 3 个测试文件（只改键期望值/辅助函数，不改业务断言）

**执行步骤**：
1. [ ] grep `_article_key\|rsplit("/"` in tests
2. [ ] 逐处替换为 canonical

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests/test_p0_asset_cache.py tests/test_idempotency_lock.py tests/test_d04_short_link.py -q
```

#### S2.3.2 ✅

**交付**：探针复跑 + 全量回归（双环境）

**执行步骤**：
1. [ ] 复制 P-3/P-4 到 tests 跑完即删，输出入 EVD-V2-02
2. [ ] 全量 failed=0

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests -q -rfs | tail -2
```

## 验收标准（独立验证者逐条判 PASS / FAIL / UNKNOWN）
- [ ] P-3 输出 `fetch_count= 2 … B.hitCache= False same_doc= False`
- [ ] P-4 输出 `PROBE2 ok False`
- [ ] `grep -n "like(f\"%{" apps/api/app/services/kb.py` 为空
- [ ] `article_identity.py` 覆盖率 100%，kb.py 不低于 86%
- [ ] 全量（双环境）failed=0

## 验证命令
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests/test_article_identity.py tests/test_kb_longlink_ingest.py -q && ! grep -n 'like(f"%{' app/services/kb.py && uv run pytest tests -q | tail -1
```

## 证据路径
`docs/06_validation/evidence/EVD-V2-02/`（README 记录：sha、命令、原始输出、PASS/FAIL 结论、验证者）

## 允许修改
- `apps/api/app/services/article_identity.py`
- `apps/api/app/services/kb.py`
- `apps/api/app/repositories/asset.py（仅 get_by_url_fragment 守卫）`
- `apps/api/tests/test_article_identity.py`
- `apps/api/tests/test_kb_longlink_ingest.py`
- `apps/api/tests/test_p0_asset_cache.py`
- `apps/api/tests/test_idempotency_lock.py`
- `apps/api/tests/test_d04_short_link.py`

## 禁止修改
- `apps/api/app/services/manifest.py`、`subscription.py`、`job_worker.py`（STEP-03/04）
- `apps/api/app/providers/**`（STEP-03）
- `apps/api/app/models/**`（本步无 DDL）
- `apps/api/tests/test_scheduler.py`（STEP-06）
- `packages/contracts/**`（STEP-01 除外）
- `apps/api/alembic/versions/**`（STEP-04/08/09 各自唯一迁移号除外）
- `.github/**`（需 D-11 授权）
- `docker/**`、`deploy/**`
- 任务书未列出的一切路径

## 依赖与阻塞
- Depends on：STEP-00R；STEP-01（S2.2 起需 ADR-0011）
- Blocks：STEP-03.3.3、STEP-04、STEP-07、STEP-10
- 阻塞条件（遇到即停）：修复需要改 content_assets 唯一约束或加列 ⇒ 停（属 STEP-04/ADR 变更）

## 建议执行档位
`sonnect`　理由：规则已由 ADR 冻结，属单模块实现 + 先红测试

## 升级条件
存量兼容（旧裸 token 键/历史 biz 锚源）出现第三种形态无法归类 ⇒ 升 opus；另：同一原子任务连续 2 次验收失败 ⇒ 停止改代码，重写任务书 / 升档 / 标 blocked（熔断）。

## 预估规模
中（约 1.5–2 人日）

## 完成定义（全项目唯一口径）
所有权内 diff 符合本卡 ∧ 验收逐条有结果 ∧ 自动测试可复现 ∧ EVD 可让一周后的人复现 ∧ `make evidence-check` 通过 ∧ 未改冻结契约（STEP-01 除外）∧ 无新增同类错误。

## 回滚
`git revert <sha>`；无数据影响。

## 执行记录（S2.1.1 + S2.1.2 + S2.1.3，起始基线 `main@b69123f`）

状态：**部分完成**。S2.1.1/S2.1.2 已交付并经第一轮独立复审处置完毕（提交 `78e3378`，
其父为 `1470b77`）；S2.1.3 本轮交付（`kb._biz_from_url` 委托解析层，提交 `c10b229`）——它在工作区的形态被
第二轮复审记为 F1/G2 两条，D-05/D-06 与下段的锚更正即其处置；S2.1.3 自身另经三份独立验证
（前两份用 A–G 分组编号与 1a–6 表格编号，合并后四项成立已修、三项复现不成立，逐条记账在
`EVD-V2-02/README.md` §4.4，本卡 D-07 申报随之而来的验证层增量）；第三份即第五轮复审，它对处置批 `b45777a`
报来三条「空过」（BD-7 认别名后不认遮蔽、重复同名定义后者静默盖掉前者、手搓 `split("?")` 解析器绕开全部
正向判据），本机三条全部复现成立，闭合为 BD-12 形状白名单 + BD-13 唯一定义 + 差分语料，记账在 §4.6，
本卡新增 D-08；
S2.1.4/S2.1.5/S2.2/S2.3 未做（`asset.py` 零改动，复审 G 段独立确认）。

交付：`apps/api/app/services/article_identity.py`、`apps/api/tests/test_article_identity.py`（14 条用例）、
`apps/api/app/services/kb.py`（仅 `_biz_from_url`，`kb.py:587-591`）、
`apps/api/tests/test_kb_longlink_ingest.py`（5 条用例 ×参数化）、
`docs/06_validation/evidence/EVD-V2-02/{README.md, prove_article_identity.py, block_article_identity_plugin.py, prove_biz_delegation.py, out_s213.txt}`。

证据（每条可由他人复跑）：
- 真实 pytest：`cd apps/api && PYTHONPATH=. python -m pytest tests/test_article_identity.py -q --noconftest` → `14 passed`
- 改前红重放：见 EVD-V2-02 §3 两条命令（红 `Interrupted: 1 error during collection` / 绿 `14 passed`）
- 纯 stdlib 证明：`prove_article_identity.py` → `合计 PASS=12 FAIL=0`、`PI-11 27/27=100.0%`
- 反证：`--self-test` → `12 个实现变异体各自让指定用例变红 + 17 个判据样本对敏感 + 4 个等价重构不假红`
- S2.1.3 委托：`prove_biz_delegation.py` 改前红 `PASS=3 FAIL=10`（rc=1）→ 改后绿 `PASS=13 FAIL=0`（rc=0）
  （判据由 11 条增至 13 条：新增 BD-12 形状白名单、BD-13 唯一定义），
  `--self-test` 前两行为三档自证（`绿 rc=0 / 目标缺失 rc=2（INCONCLUSIVE） / 有判据红 rc=1 三档分得开`，
  第二行用临时副本起**真实子进程**读回退出码，不再只看 `run()` 返回值），
  结论行 `10 个函数体变异 + 10 个判据样本对 + 7 个等价写法不假红`；原始输出 `out_s213.txt` A–H 八段，
  其中 H 段是第五轮三条空过的闭合实测（H-1/H-2 rc=1、H-3 追加式 rc=1、H-4 前置式**只**红 BD-13、H-5 定义计数）

偏离与补充登记（D-01 起，均需人工追认；不同意可单独 revert 文档，代码结论不受影响）：

| id | 内容 | 性质 |
|---|---|---|
| D-01 | 实现超出卡面字面的两条口径：`+` 按字面加号解析（防同一 base64 `__biz` 的两种书写裂成两条资产）、非 `str` 入参归零返回（`Source.url` 可为 NULL/脏类型，bytes 会产出 `b''` 型 host 使下游比较静默判错） | 行为增量，卡面未规定 |
| D-02 | 用例由卡面 7 条增至 14 条（补 host 折叠、冻结性、`+`、非 str、外链带微信参数、idx 缺省两处、`__biz` 优先） | 覆盖面增量 |
| D-03 | 新增 S2.2 待定项三条：短链带 `__biz` 时 biz 与 short_token **同时非空**（规范键须声明优先级）、外链带微信参数照解（与 `kb._biz_from_url` 既有行为一致，加 host 闸门会波及所有非微信源 ⇒ 不擅改，已钉成用例）、`idx=%20`/参数名大小写/`/S/` 大写路径属未实测口径 | 口径未定，交 ADR-0011 |
| D-04 | 验收命令等价替换：本机有 pytest 9.1.1 但无 `uv`/`pytest-cov`/`sqlalchemy` ⇒ 卡面 `uv run pytest --cov...` 改由「真实 pytest（`--noconftest`）」+「stdlib 语句覆盖」两条通道承担，原命令登记为 J-1 | 环境等价，非降低标准 |
| D-05 | 本卡文件自身被修改（勾选 + 本节），不在「允许修改」清单内；证据目录累计新增四文件（`block_article_identity_plugin.py`、`prove_biz_delegation.py`、`out_s213.txt`，另第一轮已提交的 `README.md` 改动）——落在卡面「证据路径」内，非越路径。本行原写「两文件」，第二轮复审 F 段指出与提交实数不符，已更正 | 越路径申报 + 计数更正 |
| D-06 | S2.1.3 的委托把 `+`→空格、非 str 抛错两条修复**一并带进 kb 侧**（委托即继承解析口径）；同时按第二轮复审纠正两处陈旧描述：`article_identity.py` 模块 docstring 与 `test_article_identity.py` 头注释原把「只读 `biz`」写成 kb 的**现在时**，实为改前状态；行号锚 `kb.py:587-593` → `587-591` | 文案与锚随实现同步，非行为变更 |
| D-07 | S2.1.3 验证处置批（不改 `kb.py`，`git diff c10b229 -- apps/api/app/services/kb.py` 为空）：① `prove_biz_delegation.py` 的 BD-7 改认别名（`import … as pw`、`p = parse_wechat_url`），样本对 5→6、等价写法 3→5；② `_parses()` 闸门补全到反证②通道；③ 证明脚本退出码改三档 `0/1/2`（`2`=目标函数不存在，INCONCLUSIVE），并由 `--self-test` 首道闸门实测三档互异；④ `test_kb_longlink_ingest.py` 的恒等式用例每条参数化**另带字面期望**（五个值取自磁盘 kb.py 真实执行）；⑤ 自查（`g24_static_check.py`）发现并修掉该新文件的 I001 import 段序与证明脚本的 F401 死导入。理由与复现逐条见 `EVD-V2-02/README.md` §4.4/§4.5、`out_s213.txt` C/F/G 段 | 验证层增量 + 用例判定力增量，非行为变更 |
| D-08 | S2.1.3 第五轮处置批（仍不改 `kb.py`，`git diff c10b229 -- apps/api/app/services/kb.py` 依旧为空）：堵三条**空过**——① BD-12 函数体**形状白名单**（只容 导入/赋值/返回 四类语句、只容 `parse_wechat_url` 与其别名为唯一可调用根、属性只容 `.biz`、实参必须是入参；嵌套 `def`/`class`/条件/循环/推导式/comprehension/lambda/异常 等一律越界），手搓 `split("?")` + `"bi"+"z"` 的解析器从此过不了；② `_shadowed()` 剔除被本地重新绑定的别名（`def pw` 遮蔽 `import … as pw`、`parse_wechat_url = _ext` 重绑两种形态），BD-7 不再把「名字出现过」当成「调用走的是委托」；③ BD-13 顶层同名定义**必须唯一**，且 `_top_defs()`/`get_fn_node` 按 Python 模块作用域取**末位**（改前取首位，等于证明了一段死代码）。另：BD-3 恒等式样本由 6 条字面扩为 26 条（6 字面 + 20 条**差分语料**，期望取自营运的解析层，与 `test_kb_longlink_ingest.py` 的字面锚互补——字面锚抓两侧共同退化）、`--kb=<路径>` 让三档退出码在**真实子进程**上自证、反证通道加 `_biz()` 自守（变异体导入缺失时红判据而非炸 harness）。判据 11→13、变异 5→10、样本对 6→10、等价写法 5→7 | 验证层增量，非行为变更 |

交接头目：J-1 卡面覆盖率门禁命令、J-2 `ruff check app tests` 终判（本机无 ruff，I001 已按仓库真实段序修正但属推断）、
J-3 三条未实测口径需真实抓取样本、J-4 连库全量回归（S2.3）、
J-5 `test_kb_longlink_ingest.py` 的 pytest 实跑（需 structlog+sqlalchemy，本机收集期即失败，实测见 `out_s213.txt` D 段）。

