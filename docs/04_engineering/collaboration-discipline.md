---
id: COLLAB-DISCIPLINE
type: convention
title: BotHot 多会话协作纪律（AI 会话强制规范）
status: active
owner: engineering
created: 2026-10-08
updated: 2026-10-08
---

# BotHot 多会话协作纪律

> 背景：本仓库由**单人 + 多个 AI 会话并行**开发。2026-10-08 的"输出污染"风波复盘定性：
> 绝大多数"矛盾"源于并行会话交错作业 + workdir 偏移误读 + autocrlf stat 噪音，
> 而非通道被注入。本规范把当时临时形成的正确做法固化为**强制纪律**。

## 1. 开工取证（每个会话的第一组命令，先于一切写操作）

```bash
git log --oneline -3          # HEAD 与提交链
git status --short            # 工作树状态（含他人未提交改动！）
git branch --show-current     # 当前分支
```

- **不信任记忆和上下文里的状态**——上一轮的 HEAD 可能已被并行会话推进。
- 工作树有他人未提交改动时：先评估改动内容（`git diff`），**不覆盖、不回滚**，把自己的改动与其错开。

## 2. 可信通道序（判断"输出是否真实"的优先级）

1. **git 对象库**（`git log/show/diff -S`）——最难被干扰，终审通道；
2. **直接 Read 文件 / 独立实测**（重跑测试、junitxml 落盘后交叉核对）；
3. bash 回显——**仅作参考**，与 1/2 矛盾时以 1/2 为准。

**已知噪音源**（不是攻击，别恐慌）：
- `core.autocrlf=true`：`git status` 显示 `M` 但 `git diff` 为空 → 行尾 stat 噪音，重跑即消；
- 并行会话在两次命令之间提交/改写文件 → "read 内容和我不一样"多为它因；
- workdir 偏移：pytest 必须 `cd backend`，vitest 必须 `cd frontend`，否则 import 解析到别的项目。

**铁律：判定"输出被伪造/注入"之前，必须先用 git 对象库复核。禁止基于单次异常输出宣布系统性污染。**

## 3. 提交纪律

- **单一提交身份**：本仓统一 `user.name=CodingHeader` / `user.email=coderheader@github.com`
  （`git -c` 运行时参数）。禁止混用其他身份——提交考古时身份即指纹。
- **只 add 自己名下路径**：`git add <具体路径>`，禁止 `git add -A`（会把别人的半成品一起锚定）。
- **禁止 `git rm`**（本机实证过级联删除 bug）：删文件用 `rm` + `git add <路径>` 记录。
- **改完尽快 commit 锚定**：共享工作树下，未提交的改动随时可能被并行会话误伤。
- 提交信息写清**实测证据**（passed 数 / 迁移单头 / 文件:行），供下个会话免取证采信。

## 4. 分支与工作树

- 独占会话（确认无并行作业时）可开 feature 分支；**多人/多会话并行期间禁切分支**。
- 大批量文件操作（迁移/重命名）前必须**外部备份**：`cp -r /e/Code/AideanBotHot /e/Code/_AideanBotHot_backup_$(date +%Y%m%d%H%M)`。

## 5. 文档与代码的一致性

- 文档改动唯一标准 = **与代码实证一致**；标 ✅ 必须附 `文件:行` 或命令输出。
- 长行号证据从提交态取（`git show HEAD:<path> | grep -n`），不从记忆里写。
- 每会话收尾：报告 **HEAD 哈希 + ahead 数 + 未决项清单**，作为下个会话的断点。

## 6. 长任务

- 全量 pytest 约 11 分钟：必须后台跑（`run_in_background` + `python -u`），
  junitxml 落盘后二次核对（防单次 stdout 异常）。
- 隔离 PG 用 `docker run` 独立端口（5547 等），**绝不动 5433**（那是 AideanBot 原项目的库）。

## 7. 实战教训（2026-10-08 S3 迁移沉淀）

- **后台任务禁接管道**（`cmd | tail -N` 会假死：缓冲无输出、真状态不可见）。
  改为 `cmd > 日志文件 2>&1`，日志落盘后随时 tail 进度。
- **pnpm install 卡死 = 交互确认**：node_modules 断链时 pnpm 会问
  "reinstall from scratch? (Y/n)"，后台等输入永不返回。解法：`CI=true pnpm install`
  （自动确认）或先把坏目录 `mv node_modules node_modules.broken` 再全新安装。
- **git mv 到已存在目录 = 嵌套而非替换**：`git mv src dst` 当 dst 存在时会把 src
  塞进 dst 里（src→dst/src）。正确顺序：先让 dst **彻底消失**（删内容 + rmdir），
  再 git mv。
- **目录深度变化的连锁**：`backend/tests`→`apps/api/tests` 深一层，
  测试里 `Path(__file__).parents[2]`（指仓库根）全部要 +1。
  迁移后必查：`grep -rn "parents\[" tests/`。
- **路径前缀替换的盲区**：`backend/`→`apps/api/` 覆盖不了
  `working-directory: backend`、`context: ../backend` 这类**无尾斜杠**形态。
  迁移后必查：`grep -rn "backend\b" 活配置`（词边界）。

## 8. 防复发元纪律（2026-10-08 R5 沉淀，各条均有本仓实证）

- **测试数随批次同步**：AGENTS.md 的全量测试数是批次快照，**每批收口时必须刷新**，
  禁止跨批累积——943/7（S0.1）→967/5（S2.2）→968/4（S3）三代漂移即实证。
  刷新时保留演进注释链（历史基线不删）。
- **CHANGELOG 随批切段**：`Unreleased` 只承接**当前批次**条目，批收口时切段归档
  （版本段或日期段）；跨批堆积 = 病史复发——Unreleased 一度累积 84 行横跨
  v0.6/v0.6.5/S0-S3 三个批次，切段时需靠 git log 逐条考古归属。
- **修复面以「全仓 grep 消费方」驱动**：改路径/改签名前，先 `grep -rn <旧值>`
  枚举**全部消费方**（含 scripts/、Makefile、注释与提示文案），按消费方清单逐个修，
  禁止按目录清单凭记忆修——S3 迁移修了 CI/Makefile/compose/Dockerfile/tsconfig，
  却漏了 `scripts/gen_contracts.py` 与 `scripts/preflight.sh` 两个 `backend/` 消费方
  （后者还被 Makefile:118 消费），死脚本潜伏至 R0 取证才暴露。
