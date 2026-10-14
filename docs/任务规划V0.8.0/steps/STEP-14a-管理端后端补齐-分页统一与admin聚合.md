# STEP-14a 管理端后端补齐-分页统一与admin聚合

> 基线 main@61358c3｜状态：⚪ 未开始

| 字段 | 内容 |
|---|---|
| 1 归属（执行者） | 规划方(Hark) |
| 2 验收者（与执行者分离） | 执行Agent，只输出 PASS/FAIL/UNKNOWN |
| 3 难度 / 里程碑 | 高 / M2 |
| 4 来源 | F-15/F-17；V0.7.0 docs/任务规划V0.7.0/steps/STEP-14-管理端能力面补齐.md；resources.schema.json |
| 5 目标 | 6 组管理端点按冻结契约返回统一 envelope 与分页目标壳；offset 端点加兼容层。 |
| 6 输入 | apps/api/app/api/v1/admin.py、system.py、engines.py；contracts |
| 7 输出路径 | apps/api/app/api/v1/admin.py；apps/api/app/schemas/pagination.py（若已存在则扩展）；apps/api/tests/test_admin_contract.py |
| 8 三级任务 | 见下 |
| 9 验收 | 契约测试全绿；旧前端调用不回归；CI 双绿 |
| 10 命令 | `cd apps/api && uv run pytest tests/test_admin_contract.py -q` |
| 11 证据 | docs/任务规划V0.8.0/evidence/61358c3-14a/ |
| 12 允许修改 | 上述 3 路径 |
| 13 禁止修改 | 迁移目录（不新增 DDL）；apps/web/**（归 14b） |
| 14 依赖 / 阻塞 | 01、RV / D-V3-06 BLOCKING |
| 15 档位 | T3 |
| 16 升级条件 / 规模 | 需改表结构 ⇒ 停，转 ADR / ≈1.5 人日 |

## 三级任务

### S14a.1 契约对齐
- **S14a.1.1** 列 6 组端点现状：响应形、分页参数、权限依赖
- **S14a.1.2** 逐端点映射到 resources/api.envelope 目标壳
- **S14a.1.3** 差异表入证据

### S14a.2 实现
- **S14a.2.1** 通用 `Page[T]` 响应模型 + `page/page_size` 依赖
- **S14a.2.2** offset 端点接受旧参数并换算，响应补 page 字段（不破旧客户端）
- **S14a.2.3** 错误统一走 errors.global 码表

### S14a.3 测试
- **S14a.3.1** 每端点契约测试：jsonschema 校验响应
- **S14a.3.2** 非 admin 403 / 越权 IDOR 用例
- **S14a.3.3** OpenAPI 导出供 15 生成类型
