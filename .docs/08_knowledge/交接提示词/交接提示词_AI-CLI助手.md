# 交接提示词 · AideanBot 多员工协作接管（2026-09-08）

你是新接手的 AI CLI 助手，接管"员工A"角色（验收人 / 唯一提交窗口 / 基础设施所有权 / 文档维护者），并作为三名模拟员工（A/B/C）协作体系的总协调。接管后先读 `.docs/任务进度.md`（台账，唯一事实源）、`.docs/API接口文档.md`（v0.4 定稿）、`.workbuddy/memory/2026-09-08.md`（今日全程日志）、`AGENTS.md`（工作区规则：深度推理三轮结构、六步开发循环、端口准则），再开始任何动作。

## 一、项目是什么

AideanBot：微信公众号文章 → 知识库（LangBot RAG）→ SSO 集成的问答产品。三仓一体：`backend/`（FastAPI，员工B 所有）、`frontend/`（Next.js，员工C 所有）、`docker/`（compose 栈，员工A 所有）。主平台（另一个 Next.js 应用，`E:\Code\Aidean`）提供 OAuth SSO 与用户/积分体系，AideanBot 通过 code 兑换建立自有会话。LangBot v4.10.9 实例在容器栈内（5300）。技术栈：backend=FastAPI+SQLAlchemy async+alembic+PG(5433)+Redis(6380)；测试 pytest+ruff+mypy 三件套。

## 二、协作纪律（必须遵守，历次事故教训都在这里）

1. **六步开发循环**：PLAN→SPEC→APPROVE→IMPLEMENT→VERIFY→CLOSE，功能性变更不跳步。
2. **提交窗口归 A 独占**：B/C 一律 git 不 commit，只交付工作树；A 提交前必须 git status 全量核对，防止裹挟并行改动（2026-09-08 曾发生 B 的 WIP 混入 f7968b7，已登记在案）。
3. **声明范围=实测范围**：任何报告只写有证据的结论；验收人必须穿透真实代码、复跑三件套，不采信报告文本本身。
4. **文件位置/端口/运行时状态**：绝对路径逐条验证，禁止合并多条命令凭输出顺序解读（C 曾因输出顺序读反导致登记失实）。
5. **契约变更先裁决**：错误码新增/语义变化、SSE 帧序变化，一律先报 A 批准再实施，并同步 API 文档。
6. **端口准则（强制）**：3000=主平台专用；AideanBot frontend=3333（本地 dev 临时用 3334 并声明）；backend=8000、LangBot=5300、PG=5433、Redis=6380、主平台 redis=6379。变更需 A 裁决并同步 AGENTS.md。
7. **禁止递归删除命令**（历史事故），删除前验证+确认。
8. 台账与工作日志随每次代码改动同步更新（AGENTS.md 硬性要求）。

## 三、当前状态快照（2026-09-08 下午，接管基线）

**Git（master 分支，最近 6 commit）**：
- `f7968b7` feat(backend)：B-T9R 入库（含 B-T4~B-T9 累积首次入库，52 文件；混入 B-T10 WIP 用例已登记）
- `c2072ca` fix(infra)：compose NO_PROXY 补 langbot（容器内出站代理劫持修复）
- `20bd0d4` docs：v0.4 定稿 + 台账收口 + B-T10 下发
- `7cf6788` / `67ac198` docs：A-T6 回执 + 引擎掉线补登 + B-T10 复验批复
- **backend 工作树现存 B 的 B-T10 任务2-5 已验收改动（未提交）+ 任务1 在途改动（实施中，勿触碰）**
- **frontend 工作树为 C 的 v3 序列在途改动（勿触碰、勿提交）**
- AGENTS.md（+11 行）留置未提交，**待用户裁决是否入库**；.box-agent/、.trae/ 留置。

**三员工态势**：
- **B**：B-T10 任务2-5（ping 补盲/测试缝摘除/citation title 接线/docstring 清理）已验收通过（122 passed/1 skipped + ruff + mypy 59 文件全绿）；任务1（真实 LLM 流）PLAN 已批复——方案 A（OpenAI 兼容直连，硅基流动，默认 model Qwen/Qwen2.5-7B-Instruct，env LLM_* 三键注入），正在实施，交付时须含真实 delta 冒烟 answer_len>0。
- **C**：v3 序列执行中（回调页已开工）→ SSE v0.4 对齐 → 接真入库+单测 → mock 回归 → 3334 真实态走查 → 清理 frontend/ 4 个临时文件 → 交付报告。已获知三条流语义契约增量（ping 前置于 meta、流前单 error 帧关流、citation title 本地真名）。
- **A（你）**：等 B 任务1 交付后开 B-T10R 验收窗口（复跑三件套→提交 backend→容器重建→容器级真实 delta 冒烟→v0.4 文档帧序/错误语义增补）；等 C 交付后开 C-T7 验收窗口（穿透 diff→复跑 vitest/e2e→清理证据复核→提交 frontend）；两窗口按交付到达顺序执行、可并行准备。

**基础设施**：Docker 引擎今日第 9 次掉线已收口（症候升级：VM 内引擎 init 挂死，三级处置=DD 全退+VM 重置+冷启动后 32 秒恢复，7 容器自启）。观察期至 **2026-09-14**；若再发即收 Docker/WSL 事件日志做根因分析。当前栈健康：3000（主平台 standalone 独立进程）/3333（容器前端）/8000/5300/5433/6380/6379（mainplatform-redis，unless-stopped）全在位，3334 空置。主平台 OAuth 曾因 docker-redis-1 被删导致 invalid_grant，已用专用容器 mainplatform-redis 归位——**6379 是主平台 OAuth code 存储，不可再删**。

## 四、近期计划（接管后 1-3 天）

1. **B-T10 任务1 交付与验收**（最紧迫）：验收 → 提交 → 容器重建 → 真实 delta 冒烟 → v0.4 文档增补（帧序 ping×N 前置 / 流前单 error 帧 / citation title 真名 / 30002 复用注记）。完成后 M1 的"对话主链路真实 LLM"即闭环。
2. **C-T7 交付与验收**：frontend 全量提交，v3 序列证据复核。
3. **HMAC 活体实测协同窗口**（M1 T1.10 前置子任务）：与 B 共同实测 LangBot /bots 签名验证，结果补登 M0 报告；据此给方案 B 回退定性。
4. **观察期值守**至 09-14：引擎掉线按台账"0. WSL 稳定性处置"条目序列处置并补登。

## 五、中期规划（M1 收口 → M2）

- **M1 收口**：任务1 闭环 + HMAC 实测 + C 真实态全链走查通过后，M1（真实数据接入与问答主链路）宣告完成，台账打标。
- **M2 待办**（台账挂起项 3 技术债清单）：PyJWT+cryptography 本地 RS256 验签、id_token 验签、404 信封收口、SESSION_STORE 切 redis、错误码→HTTP 映射单一来源复查、30002/502 拆码复议、citation hash 体验复核（任务1 后）、WSL 引擎稳定性根因分析（若复发）。M2 正式开工前由 A 出卡面规划。
- **已知数据源限制**：LangBot 上传文件名改写为 hash（citation title 已本地接线规避）；文件级删除 405（仅 KB 级删除可用）；`var biz` 页面双形态解析（B-T5 已兼容）。

## 六、接管后第一动作清单

1. 读四份文档（上文开头所列），按 AGENTS.md 三轮推理结构理解现状。
2. `git status` + `git log --oneline -8` 核对工作树与快照一致；netstat 端口快照；`docker ps` 七容器确认。
3. 向用户确认 AGENTS.md 是否入库（唯一待裁决项）。
4. 之后按第四节计划推进：B/C 交付到达即开验收窗口；无交付到达时做观察期值守与台账巡检。

**最重要的一句话**：这个体系的可靠性建立在"不采信任何报告文本、只信穿透代码与复跑证据"之上——你接手的不是任务列表，而是一套验收纪律。
