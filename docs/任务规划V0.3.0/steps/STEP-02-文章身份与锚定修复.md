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
1. [ ] 只写测试，模块不存在 ⇒ ImportError 即红

**验收命令**：
```bash
cd apps/api && uv run pytest tests/test_article_identity.py -q  # 改前红
```

#### S2.1.2 🛠

**交付**：`article_identity.py`：`WechatUrlParts(biz, mid, idx, sn, short_token, host)` + `parse_wechat_url(url)`；`idx` 缺省 '1'；纯函数、零 IO

**执行步骤**：
1. [ ] 实现
2. [ ] S2.1.1 转绿
3. [ ] 覆盖率 100%

**验收命令**：
```bash
cd apps/api && uv run pytest tests/test_article_identity.py -q --cov=app.services.article_identity --cov-fail-under=100
```

#### S2.1.3 🔴🛠

**交付**：`kb._biz_from_url` 改为委托 `parse_wechat_url(url).biz`（同时识别 `__biz` 与 `biz`）；补测试

**执行步骤**：
1. [ ] 先写断言 `_biz_from_url(LONG_A)!=''` 红
2. [ ] 改实现转绿

**验收命令**：
```bash
cd apps/api && uv run pytest tests/test_article_identity.py -q -k biz
```

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
