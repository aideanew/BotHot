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
