/**
 * 业务错误码 —— 与后端**错误码登记表**一一对应（先登记后实现）。
 *
 * ## 单一来源（提交态 `HEAD` 逐字核对）
 *
 * - 登记表：`backend/app/core/errors.py:9-33` —— `ERROR_CODES: dict[int, str]`（code → 标识名）
 * - 异常类：`backend/app/core/errors.py:36-233` —— 每个 `AppError` 子类以类属性钉死
 *   `code` + `http_status`；`_CODE_TO_CLASS`（`errors.py:209-233`）是 code → 类注册表。
 * - HTTP 映射：`errors.py:236-243` `http_status_for()`——**单一来源是各类的 `http_status` 类属性**，
 *   本文件的 `ApiErrorHttpStatus` 即该映射的类型化复刻。
 *
 * ## 段位约定（`errors.py:3-4`）
 *
 * `1xxxx` 用户/认证 ｜ `2xxxx` 采集/信息源 ｜ `3xxxx` 知识库/机器人 ｜ `5xxxx` 系统
 *
 * ## ⚠️ 已登记的两处契约缺口（**只记录，不在本包内“修”**）
 *
 * 1. **`50003` 未登记名称**：`ConfigurationError`（`errors.py:194-198`）的 `code = 50003`
 *    并未写进 `ERROR_CODES`。`AppError.__init__`（`errors.py:46`）取
 *    `ERROR_CODES.get(self.code, "INTERNAL_ERROR")`，故 50003 目前**回落成 INTERNAL_ERROR**。
 *    本文件按「后端实际产出」如实标注，补登记属契约变更（须先报备）。
 * 2. **前端错误表是超集**：`frontend/lib/api/http.ts:26-46` 的 `ERROR_MESSAGES` 额外含
 *    `10101 / 10102 / 30101 / 30102 / 50101`——这些码在**本后端**的 `errors.py` 里不存在
 *    （属自 AideanBot 继承的前端历史映射）。前端消费时必须容忍“后端永不产出这些码”，
 *    反之后端新增码也必须同步前端表——这正是需要单一来源的原因。
 */
export type ApiErrorCode =
  // 1xxxx 用户/认证
  | 10001
  | 10002
  | 10003
  | 10004
  | 10005
  | 10006
  // 2xxxx 采集/信息源
  | 20001
  | 20002
  | 20003
  | 20004
  | 20005
  // 3xxxx 知识库/机器人
  | 30001
  | 30002
  | 30003
  | 30004
  | 30005
  | 30006
  // 5xxxx 系统
  | 50001
  | 50002
  | 50003;

/**
 * code → 登记标识名（`errors.py:9-33`）。
 *
 * `50003` 的值是后端**当前实际行为**（回落 `INTERNAL_ERROR`，见文件头缺口 1），
 * 不是期望值。
 */
export type ApiErrorName = {
  // 1xxxx 用户/认证
  10001: "UNAUTHENTICATED";
  10002: "SSO_STATE_INVALID";
  10003: "SSO_TOKEN_EXCHANGE_FAILED";
  10004: "FORBIDDEN";
  10005: "REQUEST_INVALID";
  10006: "MALFORMED_URL";
  // 2xxxx 采集/信息源
  20001: "SOURCE_URL_UNRECOGNIZED";
  20002: "EXTRACT_FAILED";
  20003: "EXTRACT_QUALITY_LOW";
  20004: "DISCOVERY_FAILED";
  20005: "RATE_LIMITED_UPSTREAM";
  // 3xxxx 知识库/机器人
  30001: "SPACE_NOT_FOUND";
  30002: "LANGBOT_API_ERROR";
  30003: "INGEST_FAILED";
  30004: "RESOURCE_NOT_FOUND";
  30005: "JOB_STATE_INVALID";
  30006: "SPACE_NAME_CONFLICT";
  // 5xxxx 系统
  50001: "INTERNAL_ERROR";
  50002: "DEPENDENCY_UNAVAILABLE";
  /** ⚠️ 登记缺口：`errors.py` 未把 50003 写进 `ERROR_CODES`，故实际回落为 INTERNAL_ERROR */
  50003: "INTERNAL_ERROR";
};

/**
 * code → HTTP 状态（`errors.py:236-243` `http_status_for()` 的类型化复刻）。
 *
 * 权威来源仍是各 `AppError` 子类的 `http_status` 类属性；本映射仅供前端做
 * “该不该重试/该不该跳登录”的静态判断，**不得**用它替代后端真实响应码。
 */
export type ApiErrorHttpStatus = {
  10001: 401;
  10002: 400;
  10003: 401;
  10004: 403;
  10005: 422;
  10006: 400;
  20001: 400;
  20002: 502;
  20003: 422;
  20004: 502;
  20005: 429;
  30001: 404;
  30002: 502;
  30003: 502;
  30004: 404;
  30005: 409;
  30006: 409;
  50001: 500;
  50002: 503;
  50003: 500;
};

/**
 * 未登录类错误码：`UnauthenticatedError`（10001/401）与 SSO 回调失败（10003/401）。
 *
 * 对应前端 `frontend/lib/api/http.ts:49-51` `isAuthError()`——**注意前端现只判
 * `10001 / 10101`**，其中 `10101` 不在本后端错误表内（见文件头缺口 2），迁移期须对齐。
 */
export type AuthErrorCode = 10001 | 10003;
