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
lint-backend: ## 后端代码检查（与 CI 同口径：ruff check app tests，格式检查另拆非阻断目标）
	cd $(BACKEND_DIR) && ruff check app tests

.PHONY: fmt-check-backend
fmt-check-backend: ## 后端格式检查（非阻断：CI 不跑这一步，历史上这 13 份未格式化——别把它当门禁）
	cd $(BACKEND_DIR) && ruff format --check app tests

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
	@test -d apps/api/app && echo "✅ apps/api/app/ 存在" || echo "⚠️  apps/api/app/ 不存在"
	@test -d apps/web/app && echo "✅ apps/web/app/ 存在" || echo "⚠️  apps/web/app/ 不存在"
	@test -d packages/contracts/src && echo "✅ packages/contracts/src/ 存在" || echo "⚠️  packages/contracts/ 不完整"
	@test -d docs/00_governance && echo "✅ docs/00_governance/ 存在" || echo "⚠️  docs/ 不完整"

.PHONY: guard-versions
guard-versions: ## 检查版本锚点一致性（fail-closed）
	@echo "检查版本锚点一致性..."
	@nvmrc_node=$$(cat $(FRONTEND_DIR)/.nvmrc 2>/dev/null | tr -d '[:space:]'); \
	dockerfile_node=$$(grep -E 'node:[0-9]+' $(FRONTEND_DIR)/Dockerfile 2>/dev/null | head -1 | sed -E 's/.*node:([0-9]+).*/\1/'); \
	engines_node=$$(grep -A2 '"engines"' $(FRONTEND_DIR)/package.json 2>/dev/null | grep -oE '[0-9]+' | head -1); \
	pm_version=$$(grep -oE 'pnpm@[0-9]+' $(FRONTEND_DIR)/package.json 2>/dev/null | head -1 | sed 's/pnpm@//'); \
	compose_base_node=$$(sed -n '/^  frontend:/,$$p' $(DOCKER_DIR)/compose.yml 2>/dev/null | grep -m1 'BASE_IMAGE:' | grep -oE 'node:[0-9]+' | head -1 | sed 's/node://'); \
	echo "  .nvmrc node: $$nvmrc_node"; \
	echo "  Dockerfile node: $$dockerfile_node"; \
	echo "  engines.node: $$engines_node"; \
	echo "  packageManager pnpm: $$pm_version"; \
	echo "  compose BASE_IMAGE node: $$compose_base_node"; \
	rc=0; \
	if [ -z "$$nvmrc_node" ]; then echo "❌ .nvmrc 为空或不存在"; rc=1; fi; \
	if [ -z "$$dockerfile_node" ]; then echo "❌ Dockerfile 未找到 node 版本"; rc=1; fi; \
	if [ -z "$$engines_node" ]; then echo "❌ package.json engines.node 未找到"; rc=1; fi; \
	if [ -z "$$pm_version" ]; then echo "❌ packageManager 未找到 pnpm 版本"; rc=1; fi; \
	if [ -z "$$compose_base_node" ]; then echo "❌ compose 前端 BASE_IMAGE 未找到 node 锚（compose 可覆盖 Dockerfile FROM，必须同锚盯防）"; rc=1; fi; \
	if [ "$$rc" -eq 0 ]; then \
		nvmrc_major=$${nvmrc_node%%.*}; \
		if [ "$$nvmrc_major" != "$$dockerfile_node" ]; then echo "❌ .nvmrc 主版本 ($$nvmrc_major，全值 $$nvmrc_node) != Dockerfile ($$dockerfile_node)"; rc=1; fi; \
		if [ "$$nvmrc_major" != "$$engines_node" ]; then echo "❌ .nvmrc 主版本 ($$nvmrc_major，全值 $$nvmrc_node) != engines.node ($$engines_node)"; rc=1; fi; \
		if [ "$$nvmrc_major" != "$$compose_base_node" ]; then echo "❌ .nvmrc 主版本 ($$nvmrc_major) != compose BASE_IMAGE 默认 (node:$$compose_base_node)——compose 会静默覆盖 Dockerfile 锚（2026-09-30 实测 node:20 漂移）"; rc=1; fi; \
	fi; \
	if [ "$$rc" -ne 0 ]; then echo "❌ 版本锚点不一致"; exit 1; fi; \
	echo "✅ 版本锚点一致"

# ─── 证据门禁（STEP-00R S0R.4.1）────────────────────────────────
.PHONY: evidence-check
evidence-check: ## 复跑仓库内全部 stdlib 证据证明（不装依赖、不起服务）
	@set -e; \
		echo "── S0.1.2 连库 DSN 两级解析 + 拒连广播 ──"; python docs/06_validation/evidence/EVD-V2-00/prove_dsn_policy.py; \
		echo "── S0.1.2 变异反证（断言必须能红）──"; python docs/06_validation/evidence/EVD-V2-00/prove_dsn_policy.py --self-test; \
		echo "── S0.3.2 Provider 样本形状 ↔ 真实读取路径 ──"; python docs/06_validation/evidence/EVD-V2-00/prove_provider_shapes.py; \
		echo "── G-24 静态自检（ruff 子集的 stdlib 近似表 + 规则两端自证；与 ruff 的两处方向差异写在脚本头部：E501 按**列宽**与 ruff 同口径（CJK 占 2 列）、pragma 那一侧本表更严；I001 段表与成员序按 ruff 实测对齐）──"; python docs/06_validation/evidence/EVD-V2-00/g24_static_check.py; python docs/06_validation/evidence/EVD-V2-00/g24_static_check.py --self-test; \
		echo "── S0R.1 测试出站代理隔离 ──"; python docs/06_validation/evidence/EVD-V2-00R/prove_net_isolation.py; \
		echo "── S0R.1 变异反证 ──"; python docs/06_validation/evidence/EVD-V2-00R/prove_net_isolation.py --self-test; \
		echo "── 真实工具步（CI 才是终判；本机按约定不装依赖 ⇒ 缺工具就 SKIP，并以退出码 3 与 PASS 区分）──"; \
		missing=0; \
		if command -v ruff >/dev/null 2>&1; then (cd $(BACKEND_DIR) && ruff check app tests); \
		else echo "SKIP(tool missing) ruff——stdlib 近似表(g24)判不了的成员序/段序之外，终判在这一步"; missing=1; fi; \
		if command -v gitleaks >/dev/null 2>&1; then gitleaks detect --source . --config .gitleaks.toml; \
		else echo "SKIP(tool missing) gitleaks——Security 门禁的终判在这一步，本机只跑 secret_shape_scan 做召回"; missing=1; fi; \
		if [ "$$missing" -ne 0 ]; then \
			echo "⚠ evidence-check：上面的 stdlib 证据全过，但真实工具步没跑 ⇒ 退出码 3（这不是 PASS，也不是 FAIL）"; \
			exit 3; \
		fi; \
		echo "✅ evidence-check 全部通过（stdlib 证据 + 真实工具两步）"

# ─── 清理 ───────────────────────────────────────────
.PHONY: clean
clean: ## 清理构建产物
	cd $(FRONTEND_DIR) && rm -rf .next node_modules/.cache
	cd $(BACKEND_DIR) && rm -rf .pytest_cache __pycache__
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "清理完成"
