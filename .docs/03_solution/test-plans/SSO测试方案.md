# AideanBot × Aidean 主平台 SSO+余额共享 联调测试方案

## 文档信息
- **版本**: v1.0
- **创建日期**: 2026-09-18
- **测试范围**: SSO 登录链路 + 余额共享读路径
- **测试边界**: back-channel logout 列为可选项，不作为本轮验收门槛

---

## 1. 测试目标与范围

### 1.1 核心目标
验证 AideanBot 子项目与 Aidean 主平台之间的 SSO 认证和余额共享功能。

### 1.2 测试范围
- **SSO 登录链路**: 授权码流程、状态管理、会话建立
- **余额共享读路径**: 实时余额查询、变更传播
- **边界条件**: 错误处理、安全约束、性能基线

### 1.3 不在本轮范围
- back-channel logout（两端均未就绪）
- 负载测试、压力测试
- 跨浏览器兼容性测试

---

## 2. 测试层级架构（4层）

### 2.1 第0层：环境验证（快速冒烟测试）
**目标**: 验证所有依赖服务基本可用
**执行时间**: < 2分钟
**前置条件**: 无

#### 原子化测试用例
| 用例ID | 用例名称 | 操作步骤 | 预期结果 | 通过标准 |
|--------|----------|----------|----------|----------|
| L0-001 | 主平台健康检查 | `curl -s http://localhost:3000/api/v1/system/health` | HTTP 200 | 服务正常响应 |
| L0-002 | JWKS 端点可用 | `curl -s http://localhost:3000/.well-known/jwks.json` | `{"keys":[...]}`，keys>=1 | 密钥材料就绪 |
| L0-003 | OIDC 配置完整 | `curl -s http://localhost:3000/.well-known/openid-configuration` | 含 issuer/authorization_endpoint/token_endpoint | OIDC 端点齐全 |
| L0-004 | Bot 后端健康检查 | `curl -s http://localhost:8000/api/v1/system/health` | HTTP 200 | 服务正常响应 |
| L0-005 | Bot 前端可达 | `curl -s -o /dev/null -w "%{http_code}" http://localhost:3333` | HTTP 200 或 302 | 前端服务正常 |
| L0-006 | PostgreSQL 可连 | `pg_isready -h localhost -p 5433` | 返回 0 | 数据库就绪 |
| L0-007 | Redis 可连 | `redis-cli -p 6380 ping` | PONG | 缓存服务就绪 |

### 2.2 第1层：单元/集成测试（无需主平台在线）
**目标**: 验证 Bot 侧代码逻辑正确性
**执行时间**: < 5分钟
**前置条件**: Python 虚拟环境就绪

#### 原子化测试用例
| 用例ID | 用例名称 | 操作步骤 | 预期结果 | 通过标准 |
|--------|----------|----------|----------|----------|
| L1-001 | 后端单元测试 | `cd backend && .venv/Scripts/python.exe -m pytest tests/test_auth.py -q` | 12 passed | 所有测试通过 |
| L1-002 | 前端单元测试 | `cd frontend && pnpm vitest run tests/callback.spec.tsx` | 所有测试通过 | 回调页逻辑正确 |
| L1-003 | 类型检查 | `cd frontend && pnpm tsc --noEmit` | 无错误 | TypeScript 类型安全 |
| L1-004 | 代码检查 | `cd backend && ruff check .` | 无错误 | Python 代码规范 |

### 2.3 第2层：容器栈集成测试
**目标**: 验证容器化部署和服务间通信
**执行时间**: < 10分钟
**前置条件**: Docker Desktop 运行，.env 文件配置正确

#### 原子化测试用例
| 用例ID | 用例名称 | 操作步骤 | 预期结果 | 通过标准 |
|--------|----------|----------|----------|----------|
| L2-001 | 容器栈启动 | `docker compose up -d` | 所有容器状态为 running | 栈正常启动 |
| L2-002 | 端口映射验证 | `docker ps --format "table {{.Names}}\t{{.Ports}}"` | frontend:3333→3000, backend:8000, postgres:5433→5432, redis:6380→6379 | 端口映射正确 |
| L2-003 | 环境变量检查 | `docker inspect aideanbot-backend --format '{{json .Config.Env}}'` | 包含 DATABASE_URL, REDIS_URL, AIDEAN_ISSUER, AIDEAN_PUBLIC_URL, OIDC_* | 关键变量齐全 |
| L2-004 | 双 issuer 验证 | 检查 backend Env 中 AIDEAN_ISSUER 和 AIDEAN_PUBLIC_URL | AIDEAN_ISSUER=http://host.docker.internal:3000, AIDEAN_PUBLIC_URL=http://localhost:3000 | 双变量正确配置 |
| L2-005 | 容器间网络 | `docker exec aideanbot-backend ping -c 1 postgres` | ping 成功 | 后端可访问数据库 |
| L2-006 | 后端日志检查 | `docker logs aideanbot-backend --tail 20` | 无 ERROR 级别日志 | 服务运行正常 |

### 2.4 第3层：端到端真实链路测试
**目标**: 验证完整用户流程和业务逻辑
**执行时间**: < 15分钟
**前置条件**: 主平台运行，Bot 栈启动，测试账号就绪

#### 原子化测试用例
| 用例ID | 用例名称 | 操作步骤 | 预期结果 | 通过标准 |
|--------|----------|----------|----------|----------|
| L3-001 | 未登录引导 | 访问 `http://localhost:3333` | 显示未登录引导卡 | 未登录态正确 |
| L3-002 | 登录重定向 | 访问 `http://localhost:3333/api/v1/auth/login` | 302 重定向到主平台 authorize | Location 包含正确的 client_id 和 redirect_uri |
| L3-003 | 主平台登录 | 在主平台使用测试账号登录 | 登录成功，跳转回 Bot | 授权码流程正常 |
| L3-004 | 回调处理 | Bot 回调页接收 code 和 state | 会话建立，跳转首页 | 认证成功 |
| L3-005 | 会话验证 | 访问 `http://localhost:3333/api/v1/auth/me` | HTTP 200，返回用户信息 | 会话有效 |
| L3-006 | 余额查询 | 从 /me 响应中提取 wallet 字段 | 包含 balanceYuan 实时值 | 余额共享正常 |
| L3-007 | 登出功能 | 调用 `POST /api/v1/auth/logout` | 会话销毁，cookie 清除 | 登出成功 |
| L3-008 | 登出后访问 | 登出后访问 /api/v1/auth/me | HTTP 401，code=10001 | 未登录态正确 |
| L3-009 | 错误 state 测试 | 使用篡改的 state 调用 callback | HTTP 400，code=10002 | 安全约束生效 |
| L3-010 | 错误 code 测试 | 使用已用过的 code 调用 callback | HTTP 401，code=10003 | 防重放机制生效 |
| L3-011 | 余额变更传播 | 主平台侧充值后，Bot 重新调用 /me | 余额值更新 | 实时查询生效 |
| L3-012 | 双轮登录退出 | 执行两轮完整的登录-登出流程 | 两轮全绿 | 流程可复现 |

---

## 3. 测试数据准备

### 3.1 测试账号
- **主平台测试账号**: 需要预先创建
- **邮箱**: test@aidean.local（示例）
- **密码**: 测试专用密码（不入代码库）

### 3.2 环境配置
```bash
# 复制环境变量模板
cp docker/.env.example docker/.env

# 关键配置项
OIDC_CLIENT_ID=wechat-rag
OIDC_CLIENT_SECRET=<与主平台一致>
AIDEAN_ISSUER=http://host.docker.internal:3000
AIDEAN_PUBLIC_URL=http://localhost:3000
OIDC_REDIRECT_URI=http://localhost:3333/auth/aidean/callback
```

### 3.3 测试工具
- **curl**: HTTP 请求测试
- **jq**: JSON 响应解析
- **Playwright**: E2E 自动化测试（可选）
- **pytest**: Python 单元测试

---

## 4. 测试执行流程

### 4.1 执行顺序
1. **第0层** → 环境验证（必须全部通过）
2. **第1层** → 单元测试（必须全部通过）
3. **第2层** → 容器集成（必须全部通过）
4. **第3层** → 端到端测试（关键路径必须通过）

### 4.2 执行命令

#### 环境验证
```bash
# L0-001 ~ L0-007
curl -s http://localhost:3000/api/v1/system/health
curl -s http://localhost:3000/.well-known/jwks.json | jq '.keys | length'
curl -s http://localhost:3000/.well-known/openid-configuration | jq '.issuer'
curl -s http://localhost:8000/api/v1/system/health
curl -s -o /dev/null -w "%{http_code}" http://localhost:3333
pg_isready -h localhost -p 5433
redis-cli -p 6380 ping
```

#### 单元测试
```bash
# L1-001
cd E:\Code\AideanBot\backend
.\.venv\Scripts\python.exe -m pytest tests/test_auth.py -q

# L1-002
cd E:\Code\AideanBot\frontend
pnpm vitest run tests/callback.spec.tsx

# L1-003
cd E:\Code\AideanBot\frontend
pnpm tsc --noEmit

# L1-004
cd E:\Code\AideanBot\backend
ruff check .
```

#### 容器集成
```bash
# L2-001 ~ L2-006
cd E:\Code\AideanBot\docker
docker compose up -d
docker ps --format "table {{.Names}}\t{{.Ports}}"
docker inspect aideanbot-backend --format '{{json .Config.Env}}' | jq '.[] | select(startswith("AIDEAN") or startswith("OIDC"))'
docker exec aideanbot-backend ping -c 1 postgres
docker logs aideanbot-backend --tail 20
```

#### 端到端测试
```bash
# L3-001 ~ L3-12（手动或自动化）
# 详见第5节详细步骤
```

---

## 5. 端到端测试详细步骤

### 5.1 第3层测试执行指南

#### L3-001: 未登录引导
```bash
# 操作
curl -s http://localhost:3333

# 预期
页面包含未登录引导卡，无用户信息
```

#### L3-002: 登录重定向
```bash
# 操作
curl -v http://localhost:3333/api/v1/auth/login 2>&1 | grep -i location

# 预期
Location: http://localhost:3000/oauth/authorize?client_id=wechat-rag&redirect_uri=http://localhost:3333/auth/aidean/callback&state=...
```

#### L3-003: 主平台登录
```bash
# 操作（需要浏览器）
1. 访问 http://localhost:3333/api/v1/auth/login
2. 在主平台登录页面输入测试账号密码
3. 提交登录表单

# 预期
登录成功，跳转回 http://localhost:3333/auth/aidean/callback?code=...&state=...
```

#### L3-004: 回调处理
```bash
# 操作（浏览器自动处理）
回调页自动加载，转发 code 和 state 到后端

# 预期
1. 后端兑换 code 成功
2. 建立会话，设置 HttpOnly cookie
3. 页面跳转到首页
```

#### L3-005: 会话验证
```bash
# 操作（需要携带 cookie）
curl -b "aideanbot_session=<session_id>" http://localhost:3333/api/v1/auth/me

# 预期
HTTP 200
{
  "code": 0,
  "data": {
    "user": {"sub": "...", "email": "...", "nickname": "...", "tier": "..."},
    "wallet": {"balanceYuan": "...", "currency": "CNY"}
  }
}
```

#### L3-006: 余额查询
```bash
# 操作
从 L3-005 响应中提取 wallet.balanceYuan

# 预期
- 余额为字符串格式（如 "12.34"）
- 与主平台同 userId 实时一致
- 无需重启 Bot 即可反映变更
```

#### L3-007: 登出功能
```bash
# 操作
curl -X POST -b "aideanbot_session=<session_id>" http://localhost:3333/api/v1/auth/logout

# 预期
HTTP 200
{
  "code": 0,
  "data": {"logged_out": true}
}
Set-Cookie: aideanbot_session=; Max-Age=0
```

#### L3-008: 登出后访问
```bash
# 操作（不携带 cookie）
curl http://localhost:3333/api/v1/auth/me

# 预期
HTTP 401
{
  "code": 10001,
  "message": "未登录"
}
```

#### L3-009: 错误 state 测试
```bash
# 操作
curl "http://localhost:3333/api/v1/auth/callback?code=test-code&state=tampered-state"

# 预期
HTTP 400
{
  "code": 10002,
  "message": "登录状态校验失败（state 无效或已使用），请重新登录。"
}
```

#### L3-010: 错误 code 测试
```bash
# 操作（先正常登录获取 state，再用已用过的 code 重试）
# 第一次登录获取 state1
# 使用 state1 和 code1 成功登录
# 第二次使用 state2 和 code1（已用）
curl "http://localhost:3333/api/v1/auth/callback?code=code1&state=state2"

# 预期
HTTP 401
{
  "code": 10003,
  "message": "授权码兑换失败（过期或被拒绝），请重新登录。"
}
```

#### L3-011: 余额变更传播
```bash
# 操作
1. 记录当前余额 balance1
2. 在主平台侧进行充值/消费操作
3. 重新调用 /me 查询余额 balance2

# 预期
balance2 != balance1（反映最新变更）
```

#### L3-012: 双轮登录退出
```bash
# 操作
第一轮：登录 → 验证 /me → 登出 → 验证未登录
第二轮：登录 → 验证 /me → 登出 → 验证未登录

# 预期
两轮流程均成功，无状态残留
```

---

## 6. 错误处理与故障排查

### 6.1 常见错误码
| 错误码 | 含义 | 处理方式 |
|--------|------|----------|
| 10001 | 未登录 | 重新执行登录流程 |
| 10002 | state 无效 | 检查 state 生成和验证逻辑 |
| 10003 | code 无效 | 检查 code 兑换流程，确保 code 未过期/重用 |
| 50002 | 依赖服务不可用 | 检查主平台是否正常运行 |

### 6.2 已知坑位速查
| 症状 | 根因/处置 |
|------|----------|
| 容器兑换 503/50002 ConnectError | 主平台未以 HOSTNAME=0.0.0.0 standalone 运行 |
| Location 出现 0.0.0.0:3000 | 需要拦截器 fulfill 时改写为 localhost:3000 |
| 兑换 401 | 检查 AIDEAN_ISSUER 和 OIDC_CLIENT_SECRET 配置 |
| 429 限流 | 清除 Redis 中的限流键：`redis-cli -p 6380 DEL rl:login:*` |
| 3333 转发 ERR_CONNECTION_RESET | 等待 30 秒后重试，非代码问题 |
| Playwright ECONNREFUSED ::1:3000 | 设置 `NODE_OPTIONS=--dns-result-order=ipv4first` |

### 6.3 调试技巧
```bash
# 查看后端实时日志
docker logs -f aideanbot-backend

# 查看前端实时日志
docker logs -f aideanbot-frontend

# 进入容器调试
docker exec -it aideanbot-backend bash

# 检查 Redis 数据
docker exec -it aideanbot-redis redis-cli

# 检查 PostgreSQL 数据
docker exec -it aideanbot-postgres psql -U aideanbot -d aideanbot
```

---

## 7. 测试报告格式

### 7.1 报告模板
```markdown
# SSO 联调测试报告

## 测试环境
- 测试时间: YYYY-MM-DD HH:MM:SS
- 测试人员: [姓名]
- 环境配置: [Docker Compose 版本、主平台版本]

## 测试结果汇总
| 层级 | 通过用例数 | 总用例数 | 状态 |
|------|------------|----------|------|
| L0 环境验证 | X/7 | 7 | PASS/FAIL |
| L1 单元测试 | X/4 | 4 | PASS/FAIL |
| L2 容器集成 | X/6 | 6 | PASS/FAIL |
| L3 端到端 | X/12 | 12 | PASS/FAIL |

## 详细测试记录
### L0-001: 主平台健康检查
- 命令: `curl -s http://localhost:3000/api/v1/system/health`
- 结果: PASS
- 响应: 200 OK

### L0-002: JWKS 端点可用
- 命令: `curl -s http://localhost:3000/.well-known/jwks.json`
- 结果: PASS
- 响应: {"keys":[...]}

...

## 失败用例分析
### [用例ID] [用例名称]
- 失败原因: [详细描述]
- 影响范围: [影响的其他用例]
- 修复建议: [具体修复方案]

## 结论
- [ ] 已实测通过
- [ ] Mock 测试通过
- [ ] 真实态未通过或未覆盖
- [ ] 依赖 A 方的阻塞项

## 后续行动
1. [待办事项1]
2. [待办事项2]
```

### 7.2 证据收集
- **日志截图**: 包含时间戳的完整日志
- **网络请求**: 使用 curl -v 或浏览器 DevTools
- **数据库状态**: 查询关键表的数据快照
- **容器状态**: docker ps 和 docker logs 输出

---

## 8. 高性能与高拓展性考虑

### 8.1 性能优化
- **并行测试**: 独立用例可并行执行（如 L0-001 ~ L0-007）
- **缓存利用**: 测试结果可缓存，避免重复执行
- **增量测试**: 只执行变更相关的测试用例

### 8.2 拓展性设计
- **模块化**: 每个测试用例独立，易于添加新用例
- **配置化**: 测试参数可通过配置文件调整
- **自动化**: 支持 CI/CD 集成，自动触发测试

### 8.3 维护性
- **文档化**: 每个测试用例有详细说明
- **版本控制**: 测试代码与产品代码同步版本管理
- **监控**: 测试结果可接入监控系统

---

## 9. 最小原子化原则

### 9.1 原子化设计
- **单一职责**: 每个测试用例只验证一个功能点
- **独立性**: 用例之间无依赖，可单独执行
- **确定性**: 相同输入总是产生相同输出
- **快速反馈**: 每个用例执行时间 < 30秒

### 9.2 层次明确
- **第0层**: 基础设施验证（环境就绪）
- **第1层**: 代码逻辑验证（单元/集成）
- **第2层**: 部署配置验证（容器集成）
- **第3层**: 业务流程验证（端到端）

### 9.3 序号体系
- **L{层级}-{序号}**: 如 L0-001、L3-012
- **层级递进**: 低层级通过后才能执行高层级
- **失败阻塞**: 低层级失败时，高层级测试暂停

---

## 10. 执行检查清单

### 10.1 测试前检查
- [ ] 主平台服务正常运行（:3000）
- [ ] Bot 栈服务正常运行（:3333, :8000, :5433, :6380）
- [ ] 测试账号已创建且可登录
- [ ] 环境变量配置正确（特别是 OIDC_CLIENT_SECRET）
- [ ] 网络代理配置正确（NO_PROXY 白名单）

### 10.2 测试中监控
- [ ] 实时查看后端日志
- [ ] 监控容器资源使用
- [ ] 记录关键请求/响应
- [ ] 观察错误模式

### 10.3 测试后清理
- [ ] 停止容器栈（如不需要）
- [ ] 清理测试数据
- [ ] 生成测试报告
- [ ] 提交问题单（如有失败）

---

## 11. 附录

### 11.1 相关文档
- AideanBot 项目 README
- Aidean 主平台 API 文档
- Docker Compose 配置说明
- OIDC 协议规范

### 11.2 联系人
- **A 方（主平台）**: [联系方式]
- **B 方（AideanBot）**: [联系方式]
- **测试支持**: [联系方式]

### 11.3 版本历史
| 版本 | 日期 | 变更说明 |
|------|------|----------|
| v1.0 | 2026-09-18 | 初始版本，包含完整测试方案 |
