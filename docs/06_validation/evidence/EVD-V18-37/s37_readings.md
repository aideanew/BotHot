# EVD-V18-37 前后端口径收尾（执行助手）

平台 @win（Windows 10 x64），开工 head `5ec14b2`（STEP-36 收口批），时间 2026-10-24（Asia/Shanghai）。
卡面 = V0.18.0/steps/STEP-37-*.md + V0.19.0 增量 S37.5。

## S37.1 两处残留文本（P-50 / P-51）

- **P-51（bots.py test-push 路径的 savepoint 注释）**：旧文案称"`persist_web_notification` 内部的
  savepoint 回滚会把**尚未 flush 的 PushLog 一并撤销**，再由 commit 重新插入"。D-V17-03 的 SQL
  事件探针实证相反：`begin_nested()` 在 flush 待写对象**之后**才开 savepoint ⇒ PushLog 落在
  savepoint 之外，通知行回滚**不会**撤销它（EVD-V14-26 §6 的 SAVEPOINT 事件序）。注释按探针
  实证改正，**零行为变化**（`git diff` 仅注释行）。
- **P-50（直投断言文案）**：现读 `git grep "直投不落库|未预锁" apps/api` = **0 命中**——台账所指的
  旧文案已被 P-24 批修掉（现文本 `test_direct_push_persists_notification.py:176-177` 明写
  "「直投不预铸」那句已被本卡推翻，见 P-24"，且断言语义与现行四路预铸行为一致）。
  ⇒ 本项**前提已由在先批次消解**，无需改动；此读数即证据。

## S37.2 EngineReason 一套词（P-90）

- 后端 `REFUSAL_MARKERS` 三值改为与前端 `apps/web/lib/api/engines.ts` 的 `ENGINE_REASON_TEXT`
  逐值一致：`未开放，请联系管理员` / `未登记 API Key` / `暂未接入`（P-90 投诉方向：列表说什么、
  点切换就说什么）。`engines.py:145` 的 not_allowlisted 组合句去掉追加的"，请联系管理员"
  （标记词已自带），:149/:152 组合句保留各自的处置提示。
- 逐值比对用例：`test_engines_capability.py::test_refusal_markers_match_the_frontend_wording`
  ——从 `engines.ts` 原文**逐行解析** `ENGINE_REASON_TEXT`（不复制第二份真相），三值比对。
  反证：改一侧任一词 ⇒ 本用例红（比对锚定两侧源文件）。
- 随动的旧词钉子：`test_p4_engines.py:250`（"尚未实接"→"暂未接入"）、`:264`（"未配置 API Key"→
  "未登记 API Key"）。前端侧 `ENGINE_REASON_TEXT`/`ENGINE_REASON_LABEL` 未动（单一词表已成立）。
- 本机：test_engines_capability.py 44 passed、test_p4_engines.py 合并 54 passed。

## S37.3 PagedResponse 收敛 PageTargetUnified（P-96）

- `usePagedList.ts`：`PagedResponse<T>` 收敛为**单一** `PageTargetUnified<T>`
  （`{items,total,limit,offset,page,pageSize,hasMore}`，与 `app/schemas/pagination.py` 的 `Page`
  模型逐键对齐）；旧两壳联合与 `isPageShape` 分支删除；hook 消费并透出 `hasMore`
  （P-96 原话：目标壳新键此前零消费）。`totalPages` 保留（Pagination.tsx 消费面）。
- 调用方现读：`usePagedList` 当前**零页面消费方**（仅 spec）⇒"所有调用方 tsc 通过"实测为
  `tsc --noEmit` rc=0 + spec 三发绿。
- spec（w9-paged-list.spec.ts）夹具随目标壳更新，首发加 `hasMore` 消费断言（true 透出）。
- 前端全套：typecheck rc=0、`test:unit` **418 passed (418)**（50 files，含 S35.4 的 guard spec）、
  lint 0 错。

## S37.4 mock 拦截表 satisfies 生成类型 —— 停在 P-82，交回

- 现读（`lib/api/mock-routes.ts` 文件头自述 + `packages/contracts/src/index.ts:33-38` 口径）：
  契约包冻结的 6 个域 dto 是 **SQLAlchemy 列内省的持久层实体镜像**，"不是 API 响应形状"
  （例：`BotChannel.secret_enc` 在序列化器里是 `has_secret`）；identity/chat/engine 三域仍是
  `.gitkeep` 骨架。mock 表的值类型取 `lib/api/types.ts` 与各域线上响应类型。
- ⇒ "每条样例加 `satisfies <生成类型>`" 的前提（存在**API 响应形状**的生成类型）在现行
  契约包下不成立；而补齐类型 = 改 `packages/contracts/**` = 卡面 §13 明令禁止（只读生成类型）。
  P-82 已精确登记这一缺口（"已按升级条件登记 P-82 交 Contract 列"）。
- 处置：本项**停在 P-82**，交规划方裁定（契约包升级出 API 响应形状类型后，本项半小时可补；
  强用持久层 DTO 冒充响应形状 = 把 P-82 点名的错配合法化，不做）。

## S37.5 ResourceNotFoundError 固定文案（P-111① / D-V19-07，V0.19 加项）

- 先红（本机 @win）：新用例 `test_envelope.py::test_resource_not_found_message_never_echoes_the_caller_value`
  在修前跑 ⇒ **FAILED**（裸 id 被回填进 message）。
- 修法：`errors.py` 的 `ResourceNotFoundError.__init__` 固定文案"资源不存在或无权限"
  （入参保留仅为调用点兼容）；`_BARE_ID_PATTERN` 回填机制删除；13 处 f-string raise
  （bots.py ×9、chat.py ×1、hot.py ×2、langbot/client.py ×1）文案改为不带 id 的固定文案；
  `test_envelope.py:120-126` 旧钉随改（裸 id 不回显 + 可读文案形态同收敛）。
- 改后：test_envelope.py **18 passed**。前端无任何地方解析这段 message
  （`grep -rn "资源不存在或无权限" apps/web` = 0 命中，S37.5 判据）。

## @ci（推送后回填）

_（占位：交付 head 三绿 run id；后端全量计数；模块门读数。）_
