# BotHot Makefile — 统一命令入口
#
# 使用方式：make <target>
# 查看 all targets：make help

.DEFAULT_GOAL := help

# ─── 变量 ───────────────────────────────────────────
BACKEND_DIR    := backend
FRONTEND_DIR   := frontend
DOCKER_DIR     := docker
COMPOSE_FILE   := $(DOCKER_DIR)/compose.yml
PYTHON         := python3
PNPM           := pnpm

# ─── Help ───────────────────────────────────────────
.PHONY: help
help: ## 显示所有可用命令
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─── 开发环境 ───────────────────────────────────────
.PHONY: dev-backend
dev-backend: ## 启动后端开发服务（端口 3300）
	cd $(BACKEND_DIR) && uvicorn app.main:app --reload --port 3300

.PHONY: dev-frontend
dev-frontend: ## 启动前端开发服务（端口 3200）
	cd $(FRONTEND_DIR) && $(PNPM) dev

.PHONY: dev
dev: ## 同时启动前后端开发服务
	@echo "请在两个终端分别运行: make dev-backend 和 make dev-frontend"

# ─── 安装依赖 ───────────────────────────────────────
.PHONY: install-backend
install-backend: ## 安装后端依赖
	cd $(BACKEND_DIR) && pip install -e ".[dev]"

.PHONY: install-frontend
install-frontend: ## 安装前端依赖
	cd $(FRONTEND_DIR) && $(PNPM) install

.PHONY: install
install: install-backend install-frontend ## 安装全部依赖

# ─── 数据库 ─────────────────────────────────────────
.PHONY: migrate
migrate: ## 执行数据库迁移
	cd $(BACKEND_DIR) && alembic upgrade head

.PHONY: migrate-new
migrate-new: ## 创建新迁移（用法：make migrate-new MSG="描述"）
	cd $(BACKEND_DIR) && alembic revision --autogenerate -m "$(MSG)"

.PHONY: migrate-down
migrate-down: ## 回滚一个迁移
	cd $(BACKEND_DIR) && alembic downgrade -1

# ─── 测试 ───────────────────────────────────────────
.PHONY: test-backend
test-backend: ## 运行后端测试
	cd $(BACKEND_DIR) && pytest tests/ -v

.PHONY: test-frontend-unit
test-frontend-unit: ## 运行前端单元测试
	cd $(FRONTEND_DIR) && $(PNPM) test:unit

.PHONY: test-frontend-e2e
test-frontend-e2e: ## 运行前端 e2e 测试
	cd $(FRONTEND_DIR) && $(PNPM) test:e2e

.PHONY: test
test: test-backend test-frontend-unit ## 运行全部测试（不含 e2e）

.PHONY: test-all
test-all: test-backend test-frontend-unit test-frontend-e2e ## 运行全部测试（含 e2e）

# ─── 代码检查 ───────────────────────────────────────
.PHONY: lint-backend
lint-backend: ## 后端代码检查
	cd $(BACKEND_DIR) && ruff check app/ && ruff format --check app/

.PHONY: lint-frontend
lint-frontend: ## 前端代码检查
	cd $(FRONTEND_DIR) && $(PNPM) lint && $(PNPM) typecheck

.PHONY: lint
lint: lint-backend lint-frontend ## 全部代码检查

# ─── 构建 ───────────────────────────────────────────
.PHONY: build-frontend
build-frontend: ## 构建前端生产包
	cd $(FRONTEND_DIR) && NEXT_PUBLIC_API_MOCK=false $(PNPM) build

# ─── Docker ────────────────────────────────────────
.PHONY: docker-up
docker-up: ## 启动 Docker Compose 全栈
	docker compose -f $(COMPOSE_FILE) up -d

.PHONY: docker-down
docker-down: ## 停止 Docker Compose
	docker compose -f $(COMPOSE_FILE) down

.PHONY: docker-logs
docker-logs: ## 查看 Docker 日志
	docker compose -f $(COMPOSE_FILE) logs -f

.PHONY: docker-ps
docker-ps: ## 查看 Docker 容器状态
	docker compose -f $(COMPOSE_FILE) ps

.PHONY: docker-build
docker-build: ## 构建 Docker 镜像
	docker compose -f $(COMPOSE_FILE) build

# ─── 预检 ───────────────────────────────────────────
.PHONY: preflight
preflight: ## 运行预检脚本
	bash scripts/preflight.sh

# ─── 架构守卫 ───────────────────────────────────────
.PHONY: guard-ports
guard-ports: ## 检查端口分配是否正确
	@echo "检查端口分配..."
	@backend_hits="$$(grep -rn "3333" $(BACKEND_DIR)/app/ $(DOCKER_DIR)/ --include="*.py" --include="*.yml" --include="*.yaml" --include="*.sh" --include="*.env*" --include="*.example" 2>/dev/null || true)"; \
	frontend_hits="$$(grep -rn "3333" $(FRONTEND_DIR)/app/ $(FRONTEND_DIR)/lib/ $(FRONTEND_DIR)/e2e/ --include="*.ts" --include="*.tsx" --include="*.json" --include="*.mjs" 2>/dev/null || true)"; \
	rc=0; \
	if [ -n "$$backend_hits" ]; then echo "❌ 后端/编排侧发现旧端口 3333："; printf '%s\n' "$$backend_hits"; rc=1; fi; \
	if [ -n "$$frontend_hits" ]; then echo "❌ 前端侧发现旧端口 3333："; printf '%s\n' "$$frontend_hits"; rc=1; fi; \
	if [ "$$rc" -ne 0 ]; then echo "❌ 发现旧端口 3333，需清理"; exit 1; fi; \
	echo "✅ 无旧端口 3333"
	@grep -r "bothot_session" $(BACKEND_DIR)/app/ 2>/dev/null && echo "✅ session cookie = bothot_session" || \
		{ echo "❌ session cookie 名称不正确"; exit 1; }

.PHONY: guard-structure
guard-structure: ## 检查目录结构是否完整
	@echo "检查目录结构..."
	@test -d apps/api/src/modules && echo "✅ apps/api/src/modules/ 存在" || echo "⚠️  apps/api/src/modules/ 不存在"
	@test -d apps/web/src/features && echo "✅ apps/web/src/features/ 存在" || echo "⚠️  apps/web/src/features/ 不存在"
	@test -d docs/00_governance && echo "✅ docs/00_governance/ 存在" || echo "⚠️  docs/ 不完整"

.PHONY: guard-versions
guard-versions: ## 检查版本锚点一致性（fail-closed）
	@echo "检查版本锚点一致性..."
	@nvmrc_node=$$(cat $(FRONTEND_DIR)/.nvmrc 2>/dev/null | tr -d '[:space:]'); \
	dockerfile_node=$$(grep -E 'node:[0-9]+' $(FRONTEND_DIR)/Dockerfile 2>/dev/null | head -1 | sed -E 's/.*node:([0-9]+).*/\1/'); \
	engines_node=$$(grep -A2 '"engines"' $(FRONTEND_DIR)/package.json 2>/dev/null | grep -oE '[0-9]+' | head -1); \
	pm_version=$$(grep -oE 'pnpm@[0-9]+' $(FRONTEND_DIR)/package.json 2>/dev/null | head -1 | sed 's/pnpm@//'); \
	echo "  .nvmrc node: $$nvmrc_node"; \
	echo "  Dockerfile node: $$dockerfile_node"; \
	echo "  engines.node: $$engines_node"; \
	echo "  packageManager pnpm: $$pm_version"; \
	rc=0; \
	if [ -z "$$nvmrc_node" ]; then echo "❌ .nvmrc 为空或不存在"; rc=1; fi; \
	if [ -z "$$dockerfile_node" ]; then echo "❌ Dockerfile 未找到 node 版本"; rc=1; fi; \
	if [ -z "$$engines_node" ]; then echo "❌ package.json engines.node 未找到"; rc=1; fi; \
	if [ -z "$$pm_version" ]; then echo "❌ packageManager 未找到 pnpm 版本"; rc=1; fi; \
	if [ "$$rc" -eq 0 ]; then \
		if [ "$$nvmrc_node" != "$$dockerfile_node" ]; then echo "❌ .nvmrc ($$nvmrc_node) != Dockerfile ($$dockerfile_node)"; rc=1; fi; \
		if [ "$$nvmrc_node" != "$$engines_node" ]; then echo "❌ .nvmrc ($$nvmrc_node) != engines.node ($$engines_node)"; rc=1; fi; \
	fi; \
	if [ "$$rc" -ne 0 ]; then echo "❌ 版本锚点不一致"; exit 1; fi; \
	echo "✅ 版本锚点一致"

# ─── 清理 ───────────────────────────────────────────
.PHONY: clean
clean: ## 清理构建产物
	cd $(FRONTEND_DIR) && rm -rf .next node_modules/.cache
	cd $(BACKEND_DIR) && rm -rf .pytest_cache __pycache__
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "清理完成"
