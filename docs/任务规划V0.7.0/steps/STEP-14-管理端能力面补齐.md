# STEP-14 管理端能力面补齐（6 组端点无消费方）

| 字段 | 值 |
|---|---|
| 归属-切片 | S-M4 未纳管域补齐（含 UI，用户指令明列「核心+高难度尤其 UI」） |
| 归属-需求 | **REQ-F-008**（`product-requirements.md:121`）；SHOULD 组；分级依据 02 §3 |
| 归属-方案 | 04 §4.13、`contracts/ux_states.schema.json`（八态）、`contracts/api.envelope.schema.json#/x-pagination`、`contracts/identity.schema.json#/x-permission-matrix` |
| 裁决 | **D-V3-00（BLOCKING：UI 由规划方自执行，需批准）**、**D-V3-06（BLOCKING：补 UI 或显式 MUST NOT）**、D-V3-02（分页目标壳） |
| 里程碑 | M4 |
| 档位 | **opus**　理由：跨前后端契约消费 + 权限边界（admin rank）+ 新建界面骨架，属跨模块集成。**升级条件**：若 D-V3-06 判定要改后端授权面 ⇒ `fable` |
| 规模 | 大（≈2 人日；14a 0.5d + 14b 1.5d。单三级任务均 <2h） |
| 依赖 | Depends on：STEP-01（契约冻结）、STEP-16（管理面要显示告警/降级真实状态）。Blocks：STEP-15（前端契约层消费本卡 DTO） |
| 基线 | main@13acacc |
| 剩余原子任务 | 9（👤 1） |

## 目标（可验证的一句话）
以下 6 组「后端有接口、`apps/web/**` 零消费」的能力各自拥有一个可操作界面（或一条显式 MUST NOT 裁决记录）：引擎密钥登记、推送渠道、发现渠道、运维探针、推送任务/终态、SSO backchannel-logout。

## 输入
- 实测缺口（本会话 for 循环计数，`coverage §3`，全部 0 命中）：

| 端点组 | 后端锚 | 期望界面 |
|---|---|---|
| 引擎密钥 | `api/v1/admin.py:295`（GET）、`:342`（POST）、`:363`（DELETE） | `/admin/keys` |
| 推送渠道 | `admin.py:449` | `/admin/channels`（与下行合并视图） |
| 发现渠道 | `admin.py:467` | `/admin/channels` |
| 运维探针 | `admin.py:489` | `/admin/ops` |
| 推送任务/终态 | `admin.py:514` | `/admin/push` |
| backchannel-logout | `api/v1/auth.py:159` | 无 UI（服务间）⇒ 需求文本显式说明，见 S14.1.2 |
- 契约：`ux_states.schema.json#/x-core-views`（`/admin` 那条已写清六态要求）
- 权限：`identity.schema.json` — 以上端点全部 `require_roles("admin")`（rank 2）；界面必须在 rank<2 时**不渲染任何管理数据**
- 代码锚（待删）：`admin.py:522` 过期注释「本批诚实占位：校验全落地、投递未实接」，而 `services/push.py:59-62` 已实接
- 前置状态：STEP-16 已合（否则 `/admin/ops` 显示的告警态是假的，F-83）

## 输出（文件）
- 14a（后端，W-API）：`apps/api/app/api/v1/admin.py`（响应补目标分页壳与字段，不改授权语义）、`packages/contracts/src/**`（同提交重生成）、`apps/api/tests/test_admin_contract.py`
- 14b（前端，规划方自执行）：`apps/web/app/admin/keys/`、`apps/web/app/admin/channels/`、`apps/web/app/admin/push/`、`apps/web/app/admin/ops/`（各 `page.tsx` + `error.tsx` + `loading.tsx`）、`apps/web/components/admin/`、`apps/web/lib/api/admin.ts` 扩展、`docs/03_solution/design/DESIGN-admin-surfaces.md`
- `docs/06_validation/evidence/EVD-V3-14/`

## Execution Steps
1. [ ] ✅ **S14.1.1** 复跑「6 组端点 0 消费」计数命令并把当前读数入 EVD-V3-14（不许抄 01 的数）
2. [ ] 👤 **S14.1.2** D-V3-06 签字：补 UI／显式 MUST NOT。若 MUST NOT ⇒ 本卡收缩为「需求文本更正 + backlog 记录」，14b 全部取消
3. [ ] 🛠 **S14.2.1（14a）** `admin.py` 六组端点响应补目标分页壳（D-V3-02 `{items,page,pageSize,total,hasMore}`）
   - S14.2.1.1 **存量 offset 壳保持可用**（新增并行字段而非替换，避免破坏现有消费方）
   - S14.2.1.2 同提交跑 `gen_contracts`，`--check` rc=0
4. [ ] 🔴 **S14.2.2（14a）** `test_admin_contract.py`：逐端点按 `api.envelope.schema.json` 校验响应；含一条「rank<2 访问返回 10004 且 data=null」
5. [ ] 📄 **S14.3.1（14b）** `DESIGN-admin-surfaces.md`：四个界面逐态写清 initial/loading/empty/success/error/forbidden/unauthenticated/degraded 的文案、动作、可否重试（重试显隐由错误码 `retryable` 决定）
   - 设计约束（不得违反）：密钥**只显示掩码 + 是否已配置**（`resources#/ChannelSecret.x-api-surface`）；推送终态必含 `delivered/reason/retryable/dead` 四列（`events#/PushRetryState`）；三态承载**必须复用 `LoadingErrorShell.tsx`**，不得另起 UI（`ux#/x-universal-rules` 第 6 条）
6. [ ] 🛠 **S14.3.2** `/admin/keys`：引擎密钥列表 + 登记 + 删除（DELETE 前 `ConfirmModal`；后端 `:363`）
7. [ ] 🛠 **S14.3.3** `/admin/push`：推送任务与投递终态表（`:514`），死信行红色标记且**不得**显示为「成功」
8. [ ] 🛠 **S14.3.4** `/admin/channels`：推送渠道（`:449`）与发现渠道（`:467`）合并只读视图 + 每渠道 `implemented` 标识（与 STEP-13 的 `reason` 语义对齐，禁两处各造一套）
9. [ ] 🛠 **S14.3.5** `/admin/ops`：`/live`/`/ready`/告警启用态（`:489`）；**必须显示 `ALERTING_ENABLED` 实际值**（STEP-16 前置的价值在此兑现）
10. [ ] 🔴 **S14.3.6** 每界面 ≥1 个 vitest 用例覆盖八态，mock 数据由 contracts 生成物驱动（为 S15.2 前置）
11. [ ] ✅ **S14.4.1** `pnpm typecheck` + `pnpm vitest` + `pnpm build` 读数入 EVD；B-12 由 0/6 → 6/6
12. [ ] 👤 **S14.4.2** 关 mock（`NEXT_PUBLIC_API_MOCK=false`）人工逐界面走六态并截图入 EVD　人工判断标准：空态与加载态肉眼可区分；forbidden 与 empty 不混同；错误条带可复制 requestId

## 验收标准
- [ ] 6 组端点各自的消费点存在（`grep -rl` 命中数 ≥1）或有显式 MUST NOT 裁决记录
- [ ] `/admin/**` 四界面在 rank<2 时不渲染管理数据且无数据泄漏（越权用例绿）
- [ ] 任何响应/界面不出现明文密钥或可解密材料（用例断言 + 人工复核）
- [ ] 八态用例齐备；复用 `LoadingErrorShell`；无新增自造错误 UI
- [ ] 存量 offset 消费方未破坏（`test_admin_contract.py` + 全量 0 failed）
- [ ] `admin.py:522` 过期注释已删（此判据本身须先过可满足性检查，防恒红）
- [ ] CI 双绿 run id 入 EVD（依赖机）

## 验证命令
```bash
cd apps/api
for p in admin/engines/keys admin/push/channels admin/discovery/channels admin/ops/liveness admin/push; do
  printf '%-28s web-hits=' "$p"; grep -rl "$p" ../apps/web/app ../apps/web/components ../apps/web/lib | wc -l; done   # 目标：全部 ≥1
.venv/bin/python -m pytest tests/test_admin_contract.py -q -rs
python ../../scripts/gen_contracts.py --check; echo rc=$?
cd ../web && pnpm typecheck && pnpm vitest run && pnpm build
NEXT_PUBLIC_API_MOCK=false pnpm dev:   # 人工六态走查，截图入 EVD-V3-14
```

## 证据路径
`docs/06_validation/evidence/EVD-V3-14/`（含机器读数 + 人工六态截图 + 两份 run id）

## 允许修改
- 14a：`apps/api/app/api/v1/admin.py`、`packages/contracts/src/**`、`apps/api/tests/test_admin_contract.py`
- 14b：`apps/web/app/admin/**`、`apps/web/components/admin/**`、`apps/web/lib/api/admin.ts`、`docs/03_solution/design/**`
## 禁止修改
`apps/api/app/services/**`、`app/models/**`、`alembic/**`（本卡不占迁移号）、`app/core/security.py`（归 16）、`contracts/**` 冻结稿（需改则转 ADR）、`components/LoadingErrorShell.tsx`（只准复用，改它要单独评审）

## 依赖与阻塞
- Depends on：STEP-01、STEP-16
- Blocks：STEP-15
- 阻塞条件：① D-V3-00 未批 ⇒ 14b 不下发，只推 14a；② 需要新列/新表 ⇒ 停并转 ADR；③ 发现某端点授权面缺失（无 `require_roles`）⇒ **立即 blocked 上报**，属安全缺陷，不得顺手在本卡修

## 建议执行档位 / 升级条件 / 规模
`opus`（见上）；升级 `fable` 仅当触及授权语义；规模 大、≈2 人日，单原子任务 <2h。
