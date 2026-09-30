# packages/contracts — 前后端共享契约

> **状态**：W5（2026-09-30）已冻结三个**通用**类型（分页 / 响应信封 / 错误码），
> 各业务域契约仍为骨架（属 MIG-003 迁移期工作）。

## 用途

存放前后端共享的 TypeScript 类型定义，确保 API Request/Response 类型一致。

**本包是纯类型包**：零运行时依赖、零副作用，`tsc` 配置为 `emitDeclarationOnly`，
产物只有 `dist/*.d.ts`。消费侧必须用 `import type`（见下方「迁移步骤」）。

## 目录结构

```
packages/contracts/
├── src/
│   ├── common/             # ✅ 通用类型（已冻结）
│   │   ├── pagination.ts   #   PageResult<T> / PageQuery
│   │   ├── response.ts     #   ApiResponse<T>（别名 Envelope<T>）
│   │   └── errors.ts       #   ApiErrorCode / ApiErrorName / ApiErrorHttpStatus
│   ├── identity/           # ⬜ 认证契约（骨架）
│   ├── knowledge/          # ⬜ 知识库契约（骨架）
│   ├── subscription/       # ⬜ 订阅契约（骨架）
│   ├── ingest/             # ⬜ 入库契约（骨架）
│   ├── chat/               # ⬜ 问答契约（骨架）
│   ├── engine/             # ⬜ 引擎契约（骨架）
│   ├── bot/                # ⬜ 推送契约（骨架）
│   ├── hot/                # ⬜ 热点契约（骨架）
│   └── index.ts            # 统一导出（barrel）
├── package.json            # @bothot/contracts（无运行时依赖）
├── tsconfig.json           # declaration + emitDeclarationOnly → dist/*.d.ts
└── README.md               # 本文件
```

## 已冻结类型与「单一来源」对照表

每个类型都在源文件里以注释标注了单一来源（后端/前端的 `文件:行号`）。
**改类型前先改后端；只改前端会制造新的漂移。**

| 类型 | 契约 | 单一来源（提交态 HEAD） |
|---|---|---|
| `PageResult<T>` / `PageQuery` | 分页信封 `{items,total,page,page_size}` | `backend/app/api/v1/bots.py:183,324,421`；`backend/app/api/v1/hot.py:89,193,344` |
| `ApiResponse<T>`（别名 `Envelope<T>`） | 统一响应信封 `{code,message,data,requestId}` | `backend/app/core/response.py:12-16`；前端 `frontend/lib/api/http.ts:9-14` |
| `ApiErrorCode` / `ApiErrorName` / `ApiErrorHttpStatus` | 错误码登记表 + HTTP 映射 | `backend/app/core/errors.py:9-33`（表）、`:36-233`（类）、`:236-243`（映射） |

### 已知并存异形（**勿混用**，已在文件内注明）

- 分页有两套口径：bot/hot 域用 `page / page_size`；知识库/订阅/任务域仍用
  `limit / offset`（`backend/app/api/v1/spaces.py:211`、`admin.py:196`）。
  统一口径必须**先改后端**。
- `errors.py` 的 `ConfigurationError`（code `50003`）**未登记进 `ERROR_CODES`**，
  当前回落成 `INTERNAL_ERROR` 名称；`contracts` 按后端实际行为如实标注。
- 前端 `frontend/lib/api/http.ts:26-46` 的错误文案表是**超集**（多出
  `10101/10102/30101/30102/50101`，本后端不产出这些码）。

## 构建与校验

```bash
# 生成 .d.ts（产物在 dist/，已在 .gitignore 内）
node frontend/node_modules/typescript/bin/tsc -p packages/contracts/tsconfig.json

# 仅类型检查（不落盘）
node frontend/node_modules/typescript/bin/tsc -p packages/contracts/tsconfig.json --noEmit
```

## 迁移步骤（前端切换到本包）

> W5 只做**冻结**，不强制前端立刻切换。切换属独立迁移批次，按下列顺序执行：

1. **加工作区依赖**：在 `frontend/package.json` 的 `dependencies` 里加
   `"@bothot/contracts": "workspace:*"`；在 `frontend/pnpm-workspace.yaml`（或根
   `pnpm-workspace.yaml`）的 `packages` 中加入 `packages/*`，然后 `pnpm install`。
   *（未建 workspace 前，也可用 `"file:../packages/contracts"` 临时接入。）*
2. **先构建产物**：CI/本地装依赖后跑一次 `pnpm --filter @bothot/contracts build`，
   确保 `dist/index.d.ts` 存在（`types` 字段指向它）。
3. **按域逐个替换**，每替换一域跑一次 `pnpm run typecheck` + `pnpm run test:unit`：
   - `frontend/lib/api/types.ts` 的 `Envelope<T>` → `import type { ApiResponse } from "@bothot/contracts"`
     （本包已导出 `Envelope` 别名，可先零改名过渡，再统一改名）；
   - 新增域代码直接 `import type { PageResult } from "@bothot/contracts"`，
     禁止再在 `types.ts` 里手写同形状。
4. **禁止运行时 import**：本包无 JS 产物，`import { X } from "@bothot/contracts"`
   （非 `import type`）会在构建期报错——这是刻意设计，防止把类型当值用。
5. **切换后删除重复定义**：`types.ts` 中与本包重复的 `Envelope` / 分页结构删除，
   仅保留尚未提取的业务域类型。

## 维护契约（行号校准）

注释里的 `文件:行号` 锚点取自**提交态**（`git show HEAD:<path>`）。上游文件改动后行号会漂移，
校准与自检方式：

```bash
# 例：核对 PageResult 的分页键仍在 bots.py / hot.py 的对应行
git show HEAD:backend/app/api/v1/bots.py | grep -n '"page_size"'
git show HEAD:backend/app/api/v1/hot.py  | grep -n '"page_size"'
```

发现漂移时**更新注释锚点**，而不是删掉来源说明——来源可追溯是本包存在的理由。
