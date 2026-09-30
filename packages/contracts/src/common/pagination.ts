/**
 * 分页信封 —— BotHot **新增域（bot / hot）** 的分页契约。
 *
 * ## 单一来源（single source of truth，全部按提交态 `HEAD` 逐字核对）
 *
 * 后端返回体形状恒为 `{ items, total, page, page_size }`：
 * - `backend/app/api/v1/bots.py:183` —— 渠道列表 `GET /api/v1/bots` 的 `page_size` 键
 * - `backend/app/api/v1/bots.py:324` —— 推送日志 `GET /api/v1/bots/{id}/logs`
 * - `backend/app/api/v1/bots.py:421` —— 推送任务 `GET /api/v1/bots/tasks`
 * - `backend/app/api/v1/hot.py:89`  —— 热点列表 `GET /api/v1/hot/topics`
 * - `backend/app/api/v1/hot.py:193` —— 日报列表 `GET /api/v1/hot/daily/reports`
 * - `backend/app/api/v1/hot.py:344` —— Feed 流 `GET /api/v1/hot/feed`
 *
 * ## ⚠️ 已知同类异形（**勿混用**）
 *
 * 知识库 / 订阅 / 任务域沿用主平台的 `{ items, total, limit, offset }`：
 * - `backend/app/api/v1/spaces.py:211`、`backend/app/api/v1/admin.py:196`
 * - 前端对应物：`frontend/lib/api/types.ts` 的 `SpaceDocsPage`、`JobsPage`
 *
 * 两种口径并存是**存量事实**，不是笔误。本类型只冻结 bot/hot 域的 `page / page_size`
 * 语义；把 `limit / offset` 域统一到本类型属迁移期工作，**必须先改后端**（属契约变更，
 * 按 AGENTS.md「先登记后实现」须先报备），否则前端单方面切换会解析不出分页字段。
 */
export interface PageResult<T> {
  items: T[];
  /** 过滤后的总数（与 items 同谓词；分页下不虚高，非同表全量行数） */
  total: number;
  /** 页码，**从 1 起**（后端 `Query(1, ge=1)` 校验，0 会被 422 拒绝） */
  page: number;
  /** 每页条数，后端上限 100（`Query(20, ge=1, le=100)`）；越界返回 10005/422 */
  page_size: number;
}

/**
 * 分页请求入参（bot/hot 域口径）。
 *
 * 注意与 `ListSpaceDocsOptions` / `ListJobsOptions` 的区别：后者用 `limit / offset`。
 */
export interface PageQuery {
  /** 页码，从 1 起；缺省由后端回落 1 */
  page?: number;
  /** 每页条数；缺省由后端回落 20 */
  page_size?: number;
}
