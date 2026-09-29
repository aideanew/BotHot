/**
 * lib/api —— 前端 API 单一出口（T1.2.5 分域拆分后的 barrel）
 *
 * 职责（与原 lib/api.ts 完全一致）：
 * 1. 统一信封 {code, message, data, requestId} 的解包与错误归一；
 * 2. MOCK 开关：后端未就绪阶段对契约样例数据开发，不被后端进度阻塞；
 * 3. 所有页面/组件禁止自行 fetch，必须经由本模块暴露的函数访问后端。
 *
 * 分域结构（每域一文件，本文件只做转出；公开符号与拆分前**逐一对齐**）：
 *   types.ts           契约类型 + ApiError + normalizeMeData
 *   http.ts            MOCK 开关 / 错误文案 / request（内部设施 ERROR_MESSAGES 等不外转）
 *   auth.ts            认证（登录跳转 / 会话态 / 登出）
 *   spaces.ts          知识空间（增查 + 文档列表）
 *   public-library.ts  公共库（列表 / 批量引入）
 *   subscriptions.ts   整号订阅（sources / subscriptions）
 *   jobs.ts            任务域（清单分页 / 详情轮询 / 重试 / 取消，R0.4）
 *   engines.ts         引擎可插拔（列表 / 切换）
 *   admin.ts           后台管理（跨用户读面 + 批量操作，无 mock 分支）
 *   ingest.ts          链接解析入库（预校验 / resolve / extract / 提交 / 轮询）
 *   batch.ts           批量入库纯函数（批量粘贴 / 预览断点 / 轮询提示）
 *   ask.ts             问答（SSE 单事件流）
 *   mock-data.ts       跨域共享 mock 样例（内部，不外转）
 *
 * 契约来源：.docs/03_solution/interfaces/API接口文档.md（只读；发现不一致走变更单给 A）
 */

// ---------- 契约类型（全量公开） ----------
export * from "./types";

// ---------- 请求基础设施（仅公开面；ERROR_MESSAGES/friendlyMessage/delay/mockRequest 属内部） ----------
export { MOCK_ENABLED, MOCK_LABEL, isAuthError, request } from "./http";

// ---------- 各业务域 ----------
export * from "./auth";
export * from "./spaces";
export * from "./public-library";
export * from "./subscriptions";
export * from "./jobs";
export * from "./engines";
export * from "./admin";
export * from "./ingest";
export * from "./batch";
export * from "./ask";
export * from "./bots";
export * from "./hot";
