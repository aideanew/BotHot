# Changelog

本项目所有值得记录的变化都写在此文件。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

> **收录口径（重要）**：本文件**只收录已实现的事实**（含明确的“部分实现”限定语），
> 不写入计划中/在途功能。每条目末尾标注来源提交短 hash（`git log` 可对）。
> 当前仓库**尚无 tag**，故全部条目归入 `Unreleased`；正式版本段待发布节点确定后切分。

## [Unreleased]

### Added

- 六渠道推送 Provider 真实投递：飞书、钉钉、企业微信、通用 Webhook、微信 ClawBot、站内通知
  （`backend/app/providers/push/`；站内通知为 Redis pub/sub **投递侧**，前端订阅侧未实现）—— `dca56b0`
- Bot 渠道管理能力：渠道 CRUD、测试推送、推送日志、推送任务 CRUD 与手动触发
  （`backend/app/api/v1/bots.py`）—— `dca56b0`
- PushScheduler 定时调度器：60s 扫描、Cron **简版**解析（`HH:MM` / `*/N` / 纯数字分钟），
  在 backend 进程内由 FastAPI lifespan 启动（`backend/app/main.py:247`）—— `dca56b0` `1c89b2e`
- 热点域**读侧** API：热点列表/详情、日报列表/详情/生成、Feed 流
  （`backend/app/api/v1/hot.py`；聚簇为占位响应，`hot_score` 无计算，Feed 无写入方）—— `dca56b0`
- BotHot 扩展数据模型 7 张表（bot_channels / push_tasks / push_logs / hot_topics /
  hot_topic_articles / daily_reports / feed_items）+ Alembic 迁移 `ab1004bh01` —— `dca56b0`
- 前端页面：机器人管理（`/bots`）、热点中心（`/hot`）、日报（`/hot/daily`）；
  全链路端口统一 3200（dev/build/Docker）—— `dca56b0`
- 四平台文章来源 Provider：Dajiala 极致了、JustOneAPI、TikHub、Wellbyte 数井
  （`backend/app/providers/article_sources/`，含发现注册与按成本排序的付费详情兜底协调器）—— `3b548b1`
- `ConfigurationError`（code `50003`）异常类 —— `3b548b1`
- 文章采集测试证据归档：`docs/06_validation/evidence/channeltest-20260929/`
  （4 平台活体实测，TC 编号逐条可对）—— `3b548b1`
- 文档体系 `docs/`（00_governance ~ 04_engineering，23 个文件）；
  `apps/` monorepo 目录骨架；`packages/contracts/` 契约包骨架 —— `1c89b2e`
- `Makefile` 27 个 target（含 `guard-ports` / `guard-structure` 架构守卫）—— `1c89b2e`
- **共享契约冻结（W5，本分支待合并）**：`packages/contracts/` 落地
  `PageResult<T>` / `ApiResponse<T>` / `ApiErrorCode` 三类，均标注后端单一来源 `文件:行号`,
  配 `package.json` + `tsconfig.json`（`emitDeclarationOnly` → 仅产 `.d.ts`）—— W5
- **冒烟脚本（W5，本分支待合并）**：`scripts/smoke.sh`——`docker compose up -d` 后轮询
  `/api/v1/system/health` 并校验 `process_heartbeats` 中 scheduler/worker 心跳新鲜度，输出 PASS/FAIL —— W5

### Changed

- 项目由 AideanBot 升级更名为 BotHot（session cookie / 容器名 / 项目名 / 前端端口 3200）—— `dca56b0`
- 后端容器内部端口由 8000 漂移修正为 3300（与 compose、前端 rewrites 对齐）—— `1c89b2e`
- 文章来源证据口径由“行级标签”改为**格级证据**（每个 ✅/⚠️/❌ 自带 TC 编号与级别）；
  补齐实时性/标识体系/请求形态/失败计费/价格漂移五个决策维度 —— `90c4e2f`
- 计价单位纠正：TikHub 为 **USD/请求**（非 credits），Wellbyte 为 credits，
  Dajiala / JustOneAPI 为 CNY —— `90c4e2f`
- 文档状态口径修正：推送 Provider 由“占位”更正为“已实现真实投递”，
  PushScheduler 归属更正为 backend 进程内 —— `1c89b2e`
- **CI 后端测试门禁真实化（W5，本分支待合并）**：`backend` job 增加 `postgres:16` service
  （凭据/端口与 `backend/tests/conftest.py:36` 默认 DSN 对齐）与 `alembic upgrade head`
  迁移步骤；新增 skip 门禁（PG 不可达类 skip 直接失败 + skip 总数超基线失败）—— W5
- **文档漂移修复（W5，本分支待合并）**：`docs/04_engineering/roadmap.md` 回填 v0.4 勾选状态；
  `backlog.md` 将 HOT-003/HOT-004 由 ✅ 更正为 🔧 并注明缺口；`AGENTS.md` 修正站内通知/
  热点/密钥加密三处表述；`conventions.md` §6.1 补渠道密钥 base64 过渡态说明；
  `project-map.md` 将 `06_validation/` 由“预留”更正为“已启用” —— W5

### Fixed

- 双端 CI 门禁清零：backend（ruff 0.12.12 / mypy / pytest 本地全绿）；
  frontend（typecheck / vitest / build 全绿）—— `e786d78`
- `providers/article_sources/registry.py`：4 个来源工厂函数前移到 `CHANNELS` 之前，
  消除模块导入期 `NameError`（ruff F821）—— `e786d78`
- `push_scheduler.stop()`：`with` 更正为 `async with`（`_suppress_cancel` 仅实现
  `__aenter__`；原实现调用 stop() 必抛 `AttributeError`，调度器停不下来）—— `e786d78`
- 安全：`bots` / `hot` 两个 router 补 `get_current_sub` 登录门禁
  （此前两域全部端点可匿名读写）—— `e786d78`
- 前端 `bots` / `hot` / `hot/daily` 三页补 `usePageTitle`，修复页签标题覆盖守卫 —— `e786d78`
- JustOneAPI 搜索由“返回空列表”更正为真实契约级实现；
  TikHub 详情由返回 `None` 更正为调用 v2 端点（402 时降级）—— `90c4e2f`

---

## 记录约定

- 新增条目请归入 `Unreleased` 对应小节（Added / Changed / Fixed / Removed / Security）。
- **禁止把未实现或仅计划中的功能写进来**——本仓库的历史问题是文档虚报状态，
  条目须能被 `git log` 或代码实证核对。
- 发布时把 `Unreleased` 段落改名成 `## [x.y.z] - YYYY-MM-DD`，并新增空的 `Unreleased`。
