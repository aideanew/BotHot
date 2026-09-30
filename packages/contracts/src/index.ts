/**
 * `@bothot/contracts` —— BotHot 前后端共享契约包（**纯类型**）。
 *
 * 纪律：
 * 1. 零运行时依赖、零副作用：本包**只导出类型**，`tsc` 配置为 `emitDeclarationOnly`，
 *    产物仅 `dist/*.d.ts`（见 `tsconfig.json`）。因此消费侧必须用 `import type`。
 * 2. **每个类型都在其源文件里标注了“单一来源”**（后端/前端的具体 `文件:行号`）。
 *    新增类型前先确认后端形状，**禁止按想象定义**（本仓库最大的病史是文档/契约虚报）。
 * 3. 行号锚点取自**提交态**（`git show HEAD:<path>`）。上游文件被改动后行号会漂移，
 *    校准方式见 README「维护契约」。
 *
 * 当前已冻结（W5）：
 * - 通用：分页 `PageResult<T>` / 响应信封 `ApiResponse<T>` / 错误码 `ApiErrorCode`
 *
 * 尚未冻结（保持骨架目录）：identity / knowledge / subscription / ingest / chat / engine / bot / hot
 * ——各域契约提取属迁移期工作（MIG-003）。
 */
export type { PageQuery, PageResult } from "./common/pagination";
export type { ApiFailure, ApiResponse, ApiSuccess, Envelope } from "./common/response";
export type {
  ApiErrorCode,
  ApiErrorHttpStatus,
  ApiErrorName,
  AuthErrorCode,
} from "./common/errors";
