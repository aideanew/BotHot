# BotHot Makefile — 统一命令入口
#
# 使用方式：make <target>
# 查看 all targets：make help

.DEFAULT_GOAL := help

# ─── 变量 ───────────────────────────────────────────
BACKEND_DIR    := apps/api
FRONTEND_DIR   := apps/web
DOCKER_DIR     := docker
COMPOSE_FILE   := $(DOCKER_DIR)/compose.yml
PNPM           := pnpm
# STEP-00X：命令实体的唯一源是 scripts/entry.py；make 只做薄转调，
# 保证 `make X` 与 `python scripts/entry.py X` 同退出码。
# 这里的 ifeq 是**全仓第二处、也是唯一一处**平台分支（另一处在 entry.py 的 dispatch()）：
# Windows 上 `python3` 解析到 Microsoft Store 的空壳 stub，调用它什么都不发生、退出码还是 0
# ——那正是"没装却长得像通过"的假读数，所以 Windows 分支必须用 `python`。
ifeq ($(OS),Windows_NT)
PYTHON         := python
ENTRY          ?= python scripts/entry.py
GUARDS         ?= python scripts/guards.py
else
PYTHON         := python3
ENTRY          ?= python3 scripts/entry.py
GUARDS         ?= python3 scripts/guards.py
endif

# ─── Help ───────────────────────────────────────────
.PHONY: help
help: ## 显示所有可用命令
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─── 开发环境 ───────────────────────────────────────
.PHONY: dev-backend
dev-backend: ## 启动后端开发服务（端口 3300）
	@$(ENTRY) dev-backend

.PHONY: dev-frontend
dev-frontend: ## 启动前端开发服务（端口 3200）
	@$(ENTRY) dev-frontend

.PHONY: dev
dev: ## 同时启动前后端开发服务
	@$(ENTRY) dev

# ─── 安装依赖 ───────────────────────────────────────
.PHONY: install-backend
install-backend: ## 安装后端依赖
	@$(ENTRY) install-backend

.PHONY: install-frontend
install-frontend: ## 安装前端依赖
	@$(ENTRY) install-frontend

.PHONY: install
install: install-backend install-frontend ## 安装全部依赖
	@:  # 由前置目标转调，本体不重复执行

# ─── 数据库 ─────────────────────────────────────────
.PHONY: migrate
migrate: ## 执行数据库迁移
	@$(ENTRY) migrate

.PHONY: migrate-new
migrate-new: ## 创建新迁移（用法：make migrate-new MSG="描述"）
	@BOTHOT_MSG="$(MSG)" $(ENTRY) migrate-new

.PHONY: migrate-down
migrate-down: ## 回滚一个迁移
	@$(ENTRY) migrate-down

# ─── 测试 ───────────────────────────────────────────
.PHONY: test-backend
test-backend: ## 运行后端测试
	@$(ENTRY) test-backend

.PHONY: test-frontend-unit
test-frontend-unit: ## 运行前端单元测试
	@$(ENTRY) test-frontend-unit

.PHONY: test-frontend-e2e
test-frontend-e2e: ## 运行前端 e2e 测试
	@$(ENTRY) test-frontend-e2e

.PHONY: test
test: test-backend test-frontend-unit ## 运行全部测试（不含 e2e）
	@:  # 由前置目标转调，本体不重复执行

.PHONY: test-all
test-all: test-backend test-frontend-unit test-frontend-e2e ## 运行全部测试（含 e2e）
	@:  # 由前置目标转调，本体不重复执行

# ─── 代码检查 ───────────────────────────────────────
.PHONY: lint-backend
lint-backend: ## 后端代码检查（与 CI 同口径：ruff check app tests，格式检查另拆非阻断目标）
	@$(ENTRY) lint-backend

.PHONY: fmt-check-backend
fmt-check-backend: ## 后端格式检查（非阻断：CI 不跑这一步，历史上这 13 份未格式化——别把它当门禁）
	@$(ENTRY) fmt-check-backend

.PHONY: lint-frontend
lint-frontend: ## 前端代码检查
	@$(ENTRY) lint-frontend

.PHONY: lint
lint: lint-backend lint-frontend ## 全部代码检查
	@:  # 由前置目标转调，本体不重复执行

# ─── 构建 ───────────────────────────────────────────
.PHONY: build-frontend
build-frontend: ## 构建前端生产包
	@$(ENTRY) build-frontend

# ─── Docker ────────────────────────────────────────
.PHONY: docker-up
docker-up: ## 启动 Docker Compose 全栈
	@$(ENTRY) docker-up

.PHONY: docker-down
docker-down: ## 停止 Docker Compose
	@$(ENTRY) docker-down

.PHONY: docker-logs
docker-logs: ## 查看 Docker 日志
	@$(ENTRY) docker-logs

.PHONY: docker-ps
docker-ps: ## 查看 Docker 容器状态
	@$(ENTRY) docker-ps

.PHONY: docker-build
docker-build: ## 构建 Docker 镜像
	@$(ENTRY) docker-build

# ─── 预检 ───────────────────────────────────────────
.PHONY: preflight
preflight: ## 运行预检脚本
	@$(ENTRY) preflight

# ─── 架构守卫 ───────────────────────────────────────
.PHONY: guard-ports
guard-ports: ## 检查端口分配是否正确
	@$(GUARDS) guard-ports

.PHONY: guard-structure
guard-structure: ## 检查目录结构是否完整
	@$(GUARDS) guard-structure

.PHONY: guard-versions
guard-versions: ## 检查版本锚点一致性（fail-closed）
	@$(GUARDS) guard-versions

# ─── 证据门禁（STEP-00R S0R.4.1）────────────────────────────────
.PHONY: evidence-check
evidence-check: ## 复跑仓库内全部 stdlib 证据证明（不装依赖、不起服务）
	@$(GUARDS) evidence-check

# ─── 治理门禁（STEP-00T S00T.V14.1/V14.2）─────────────────────────
.PHONY: rounds-check
rounds-check: ## D-14 轮次熔断：同一卡在第 3 轮返工即红（阈值 ≤2 轮，D-V11-04）
	@$(GUARDS) rounds-check

# 聚合门：04 §8 的完成定义引用 `make guard`，而此目标此前并不存在（F-V14-09）。
# 用前置目标的既有写法（同 `test:`/`lint:`），本体不重复执行。
# 任一子门非 0 即失败——含 evidence-check 的 rc=3「工具缺席」态，那不是通过。
.PHONY: guard
guard: guard-ports guard-structure guard-versions rounds-check evidence-check ## 全部架构/证据/治理门
	@:  # 由前置目标转调，本体不重复执行

# ─── 清理 ───────────────────────────────────────────
.PHONY: clean
clean: ## 清理构建产物
	@$(ENTRY) clean
