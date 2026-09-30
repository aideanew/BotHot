/**
 * 统一响应信封 —— 全站 Response 契约。
 *
 * ## 单一来源（提交态 `HEAD` 逐字核对）
 *
 * - 后端：`backend/app/core/response.py:12-16` —— `Envelope(BaseModel)`：
 *   `code: int = 0` / `message: str = "ok"` / `data: object | None = None` / `requestId: str`
 *   构造入口：`success()`（`response.py:19-20`）、`failure()`（`response.py:23-24`）。
 * - 前端：`frontend/lib/api/http.ts:9-14` —— `Envelope<T>`，字段同名同序，
 *   解包规则 `body.code !== 0 → throw ApiError`（`http.ts:107-114`）。
 *
 * ## 与任务书简称的差异（**以代码为准，此处刻意不缩写**）
 *
 * 任务书写的是 `ApiResponse<T> = { code, message, data }`；真实信封**多一个必填
 * `requestId`**（`response.py:16`，由 `RequestIdMiddleware` 注入，与响应头
 * `X-Request-ID` 及日志三者一致）。省掉它会让类型与线上报文不一致——按
 * 「契约须从真实代码反推」的口径，此处保留该字段。
 *
 * ## data 的可空性
 *
 * 后端标注为 `object | None`，故泛型取 `T | null` 而非 `T`。前端既有 `Envelope<T>`
 * 写成 `data: T`（`http.ts:12`）——那是**前端侧的乐观标注**，不反映后端默认值。
 * 消费方仍应把 `data === null` 当合法态处理（例如删除类接口只回 `{ id }`）。
 */
export interface ApiResponse<T> {
  /** `0` = 成功；非 0 = 业务错误（取值见 `ApiErrorCode`） */
  code: number;
  /** 可直接展示的文案；成功时为 `"ok"` */
  message: string;
  /** 业务载荷；后端默认 `None`，故可为 null */
  data: T | null;
  /** 请求追踪 id（后端由 RequestIdMiddleware 注入，**恒有值**） */
  requestId: string;
}

/**
 * 前端既有命名别名。
 *
 * `frontend/lib/api/types.ts:9-14` 把同一形状命名为 `Envelope<T>`；本包以后端名
 * （`ApiResponse`）为主名，同时导出别名，使迁移期 `import type { Envelope }` 可零改名切换。
 */
export type Envelope<T> = ApiResponse<T>;

/** 成功判定：唯一的“成功”判据是 `code === 0`，不是 HTTP 2xx。 */
export type ApiSuccess<T> = ApiResponse<T> & { code: 0; data: T };

/** 失败判定：非 0 code 恒伴随可读 `message`（后端 `failure()`，`response.py:23-24`）。 */
export type ApiFailure = ApiResponse<null> & { code: Exclude<number, 0> };
