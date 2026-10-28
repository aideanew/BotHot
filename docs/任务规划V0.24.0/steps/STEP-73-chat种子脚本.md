# STEP-73：`/chat` 可检索种子

## 1. 归属

- 所属切片：P-C 供给层
- 来源需求：`02` M-8；`01` §2.5 的 `asset.py:249-256` 硬条件
- 来源方案：D-V24-12
- 执行者：执行助手

## 2. 目标

库里存在一条「空间 `langbot_kb_uuid` 非空 + 文档 `status="READY"` 且 `langbot_file_id="fake-doc-1"`」的种子，使得 `chat.py` 的 `allowed_file_ids` 非空，假 LangBot 返回的 `file_name="fake-doc-1"` 能通过 `_filter_by_allowed`。

## 3. 输入

- 文档：`01` §2.5、`03` §1 的 D-V24-12
- 契约（实体列，**逐列照抄，不许按字段名猜**）：
  - `KnowledgeSpace`：`user_id`(FK,非空)、`name`(非空)、`langbot_kb_uuid`、`status`(默认 ACTIVE)、`engine`(默认 builtin)、`engine_kb_id`；`(user_id,name)` 唯一
  - `ContentAsset`：`source_id`(FK,非空)、`content_hash`(非空,**无默认**)、`content_markdown`(非空)、`title`、`url`、`external_id`、`content_type`、`status`(默认 READY)
  - `KnowledgeDocument`：`asset_id`(FK)、`space_id`(FK)、`langbot_file_id`(默认 "")、`content_hash`(默认 "")、`status`(默认 FETCHED)
- 前置任务：STEP-72
- 前置状态：假 LangBot 已在 3291 起得来

## 4. 输出

- 新增：`scripts/e2e/seed_chat_space.py`
- 修改：`scripts/e2e/run_real_backend.sh`（在 `:299` 的种子步骤之后调用它，并把打印的 space id 写入 seed 文件）
- 新增：`docs/06_validation/evidence/EVD-V24-73/`

## 5. Execution Steps

1. [x] **S73.1** 读 `apps/api/scripts/qa_seed_sessions.py`，复用它建出的用户（取 `users` 表里 `is_admin` 的那位，或 `E2E_SEED_FILE` 里给的那位），**不另建用户体系**
2. [x] **S73.2** 写 `seed_chat_space.py`（异步 SQLAlchemy，复用 `apps/api/app/models/entities.py` 与 `app.core.db` 的 session 工厂）：
   - `KnowledgeSpace`：`name="R24 流式验收空间"`、`langbot_kb_uuid="fake-kb-1"`、`engine="builtin"`、`engine_kb_id="fake-kb-1"`
   - `ContentAsset`：`title="R24 假文章"`、`url="http://127.0.0.1:3291/fake-article"`、`content_hash=<64 位固定串>`、`content_markdown="<固定正文>"`
   - `KnowledgeDocument`：`langbot_file_id="fake-doc-1"`、`status="READY"`、`content_hash` 同上
   - 幂等：按 `(user_id, name)` 查，已存在则复用并修正 `langbot_kb_uuid` / `status` / `langbot_file_id`，**不重复插**
   - 最后 `print(space_id)` 到 stdout
3. [x] **S73.3** 启动器在 `qa_seed_sessions.py` 之后调用本脚本，把 space id 追加进 `$SEED_FILE`（供 Playwright 通过环境变量读）
4. [x] 自测：

   ```bash
   cd apps/api && python scripts/seed_chat_space.py   # 打印 space id
   ```

   实做路径按 §9 落 `scripts/e2e/seed_chat_space.py`（见 `EVD-V24-73/s73_readings.md` §3.1），故命令是
   `cd apps/api && python ../../scripts/e2e/seed_chat_space.py`。本机无 PG ⇒ 真库读数取自 CI 的
   `e2e-real`（`7853517` / run `40710695630` / job `122897048364`），`space_id=58362bde…` 与两遍计数见
   `s73_readings.md` §5.2。

5. [x] 本卡单独提交并推送

## 6. 验收标准

- [x] `python -c "import ast;ast.parse(open('scripts/e2e/seed_chat_space.py').read())"` 通过
- [x] 连跑两次：第二次不新增行（`select count(*)` 前后相同）
- [x] 跑完后 `select langbot_file_id, status from knowledge_documents where space_id=<id>` 得 `fake-doc-1 | READY`
- [x] 跑完后 `select langbot_kb_uuid from knowledge_spaces where id=<id>` 非空
- [x] 假 LangBot 的 `file_name` 与种子 `langbot_file_id` **逐字相同**（`grep` 两侧）
- [ ] `ask` 的 SSE 里出现 `delta` 帧（不是 `error` 30002）——未证：需真库 + 假上游同时在跑，归 STEP-60（见 `EVD-V24-73/s73_readings.md` §2 该行）
- [x] 本卡不改 `apps/api/app/**`、不改 `models/entities.py`

## 7. 验证命令

```bash
cd /d/Code/AideanBotHot
python -c "import ast;ast.parse(open('scripts/e2e/seed_chat_space.py',encoding='utf-8').read());print('ok')"
grep -n "fake-doc-1" scripts/e2e/seed_chat_space.py scripts/e2e/fake_langbot.py
cd apps/api && python scripts/seed_chat_space.py
```

## 8. 证据路径

`docs/06_validation/evidence/EVD-V24-73/`

## 9. 允许修改

- `scripts/e2e/seed_chat_space.py`（新增）
- `scripts/e2e/run_real_backend.sh`（仅种子步骤那一段）
- `docs/06_validation/evidence/EVD-V24-73/**`

## 10. 禁止修改

- `apps/api/app/**`（含 `models/entities.py`、`repositories/asset.py`）
- `apps/api/scripts/qa_seed_sessions.py`（复用，不改）
- `apps/api/alembic/**`（零迁移）
- `apps/web/**`、`packages/contracts/**`

## 11. 依赖与阻塞

- Depends on：STEP-72（`fake-doc-1` 这个值由 72 定义）
- Blocks：STEP-60
- 阻塞条件：
  - `entities.py` 里有本卡第 3 节没列到的非空列 ⇒ 按实际列补，**不改实体**
  - 出现「必须建用户」的情形 ⇒ 先读 `qa_seed_sessions.py`，仍无法复用它建的账号 ⇒ 停手交回（说明种子链比本卡假设的更长）

## 12. 建议执行档位

sonnet。理由：按实体列写插入，无架构判断。

## 13. 升级条件

- 需要改实体或迁移才能建种子 ⇒ 立即停手升级（那是产品改动，不在本版）

## 14. 预估规模

小，≈0.3 人日，小于 2 小时。

## 15. 熔断

同一判据 2 轮未过 ⇒ 停手，登 P 号。

## 16. 交接物

`EVD-V24-73/` 要含：两次连跑的计数（证幂等）、三张表的实际列值、`ask` 的 `delta` 帧原文。并在证据里写明「**直写表是测试夹具，不是产品路径**」（D-V24-12）。
