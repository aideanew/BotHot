# EVD-V18-39 · STEP-39 发布 v1.1.0

> 基线 `main@9544ef3`（STEP-33 收口批）｜版本 V0.18.0｜队列第三项
> 归属 Agent-Doc｜依据 D-V18-01、D-V18-02、D-V18-13；输入含 STEP-12 的 `EVD-V17-12` §6
> 发布动作（搬空 `[Unreleased]` + 打 tag + 推 tag）由用户 2026-10-23 的队列指令授权，
> 不是执行方自作主张——STEP-12 当年刻意**不**做这三步并把理由写进 §5.1，本卡正是接那一步。

## 0. 本批改动面（对照卡面 §7/§12）

| 文件 | 改动 |
|---|---|
| `CHANGELOG.md` | `[Unreleased]` 整体搬空并留一行说明；候选段标题定为 `## [v1.1.0] - 2026-10-23`；引言重写；六条 Unreleased 并入三段；两条发布阻断项（STEP-32/33）新增；候选段里一条重复条目去重、一条来源挂错已更正 |
| `AGENTS.md` | 「当前项目状态」的版本块由 v1.0.0 改为 v1.1.0 |
| git tag `v1.1.0` | 注释标签，打在发布批上（S39.3 的后半） |
| `docs/06_validation/evidence/EVD-V18-39/` | 本目录 + `s39_hash_audit.txt` |

禁止面：`§13` 的"任何代码"一行未碰（本批只有两个 md + 证据目录 + tag）；
既有 tag `v1.0.0` **未移动未删除**，也没有任何强推。

## 1. 发布前现读（`9544ef3`）

| 项 | 读数 |
|---|---|
| `git rev-list --count v1.0.0..HEAD` | **304**（发布批自身 +1 ⇒ tag 指向的提交上是 305） |
| `git tag -l` | `local-recovery-42a21f2`、`local-recovery-6751185`、`v1.0.0` |
| `git ls-remote --tags origin` | 远端**只有** `refs/tags/v1.0.0`（对象 `8ecf322…`）与 `refs/tags/v1.0.0^{}`（提交 `c19fe879…`）——两个 `local-recovery-*` 是**本地遗留**，不推、不删（指向 2026-10-21 的 docs 提交，别的一次事故恢复点，不属于本卡所有权） |
| `v1.0.0` 的形态 | **注释标签**：`git cat-file -t v1.0.0` = `tag`，标签对象 `8ecf322`，被标提交 `c19fe87` |

⚠ 一条读法坑（AGENTS.md 里也写了提醒）：`git rev-parse v1.0.0` 给的是**标签对象**的 sha，
不是被标的提交；本轮一开始就把它读成"tag 落在 8ecf322"，与旧 AGENTS.md 的"落在 c19fe87"看似矛盾，
实际是同一个标签的两种 sha。要打/读注释标签就得分别用 `v1.1.0` 与 `v1.1.0^{}`。

## 2. S39.1：`[Unreleased]` 六条的去向（合并 + 去重 + 来源）

| 原 Unreleased 条目 | 去处 | 来源短 hash（`git log -1` 复核过主语） |
|---|---|---|
| AuthGate 统一未登录守卫（G1-G4） | Added 末条 | `793288e` "feat(web): AuthGate 统一未登录守卫——九页形态收敛 + TopBar guest 登录入口（G1-G4）" |
| trunk.spec ① 断言同步 | **并进 AuthGate 那条**（它就是同批的测试同步，单列会把一条变更拆成两条事实） | 同上 `793288e` |
| 九页未登录形态收敛（G2） | Changed 新增 | `793288e`（同一提交的主体面） |
| TopBar guest 态增强（G3.1）+ 锁形徽标（G3.4） | Changed 合成一条"两处口径"（同一组件的同一状态机，两条各自引一半事实会读不出最终形态） | `793288e`、`7cf145b` |
| Security 工作流双红灯修复（trivy 幽灵版本 / Next 14→15.5.27 / mock e2e ⑦） | Fixed 新增（三个子根因逐条写） | `d0b5760`（一个提交同时修三处，主语里就写着这三条） |

新增两条发布阻断项：STEP-32 `da09dd1`、STEP-33 `c9287a6`（都进 Fixed；
STEP-32 里顺带写明新增的守卫 `guard-ci-secret-mask` 与三处接线，STEP-33 写明"不读 input/ctx"的口径）。

候选段自身另有一处**重复**：`健康/就绪探针有界化` 出现了两次（一次带 hedge、一次不带）。
本卡只合并候选段（历史段 v1.0.0 及更早**一行未动**），保留带 hedge 的那条并把来源改成真实提交。

### 2.1 一条主语复核的结果：来源挂错了
候选段把"健康/就绪探针有界化"挂在 `a3ad07a`、`0c1815c` 上，而逐个 `git log -1` 的结果是：

- `a3ad07a` = `chore(STEP-00H): skip 基线 443 → 444——门第二次按设计把我自己新增的连库用例抓出来`
- `0c1815c` = `ci(STEP-00H S00H.2.3 第 1 轮): 多平台门收口，CI-Windows --timeout 300→120`

两条的主语都不是探针本体。真正的来源用 `git log -S degraded` 与 `git log --grep STEP-00H` 现读定为
`5e5ab17` = `feat(STEP-00H S00H.1.1-1.3): 探针两层上界 + 端点预算; 顺带修限流豁免集的两个死条目`。
CHANGELOG 里把这条更正**写在条目自身来源注里**（不静默改写），skip 基线那两笔仍归位到它们自己的条目。

## 3. S39.2：AGENTS.md 版本块为什么"不抄自己的 sha"
旧块写"tag 落在 `c19fe87`"是可行的，因为那是**上一次**发布的提交，早就存在。
本次如果照抄"tag 落在 <本次发布批>"就会写下一句当时还不存在的事实（自指）。
所以新块给的是**取读数的命令**（`git ls-remote --tags origin v1.1.0`、`git rev-parse v1.1.0^{commit}`），
并把 sha 记在本 EVD 的 §5（发布后才填），两处各得其所。

## 4. 发布批推送前的本地门

| 门 | 读数 |
|---|---|
| `python scripts/guards.py evidence-check --base HEAD`（读索引） | rc=0，含 gitleaks 历史扫描 no leaks |
| `python scripts/guards.py guard-ci-secret-mask` | rc=0（本批不碰工作流，门仍绿是回归） |
| `python scripts/check_docs_consistency.py` | rc=0 |
| CHANGELOG/AGENTS 的表格与行完整性 | 逐行脚本核验：`## [v1.0.0]` 起 **305 行历史内容逐行等值**未动；候选段既有条目按 10 个探针串核验全部在位；文件 415 行 → 426 行 |

> 写入方式是"预写守卫"脚本（边界行必须逐字且唯一命中、行号落在预期窗口、组装后校验历史段逐行等值、
> 行数增量在窗口内，任一不符就不落盘）。原因写在 §7.1。

## 5. S39.3 / S39.4 发布读数（原始件 `s39_release_readings.txt`）

| 项 | 读数 |
|---|---|
| 发布批提交 | `49c3bed64307696fc65981c5eea516e70102f20f`（`docs(STEP-39 发布批): v1.1.0 定稿…`），push `9544ef3..49c3bed` |
| 三绿（同一 head、attempt 1、event=push） | CI **39929536898** success / Security **39929536900** success / CI-Windows **39929536974** success |
| tag | 注释标签 `v1.1.0`：标签对象 `db9205df7fc7a55bf5653e33e368b6cb8e128d75` → 被标提交 `49c3bed…`；`git push origin v1.1.0` 输出 `* [new tag] v1.1.0 -> v1.1.0` |
| 远端核验 | `git ls-remote --tags origin` 里 `refs/tags/v1.1.0` 与 `refs/tags/v1.1.0^{}` 两行齐备，后者正是三绿的 `49c3bed`；`v1.0.0` 两行原样未动 |
| tag 是否另触发 CI | **没有**（三个 workflow 都只在分支 push 上跑）⇒ 按卡面"tag 触发**或同 head**"读同 head 那三条 |
| S39.4 冒烟（run 39929536898 的 `compose-smoke`） | `smoke:1134` backend 存活、`smoke:1138/1139` scheduler/worker 心跳 age=2s、`smoke:1141` **结果：PASS=3 FAIL=0** |
| 区间计数复核 | `git rev-list --count v1.0.0..HEAD` 在发布批上现读 = **305**（与 CHANGELOG 引言一致） |
| 迁移面复核（写进 tag message 的那句"三次迁移均为新增"） | `git diff --name-status v1.0.0..HEAD -- apps/api/alembic/versions` = 3 个文件、状态全是 `A`（`ab1006c1a`、`ab1006c2a`、`ab1006c4a`）⇒ 无删除无改名 |

### 5.1 没有做的事（判据要求"不得出现"的几项）
- 没有强推：两次都是 fast-forward（`9544ef3..49c3bed`、tag 新建）。
- 没有移动或删除任何既有 tag：`v1.0.0` 的两行在推送前后逐字相同。
- 本地遗留的 `local-recovery-42a21f2` / `local-recovery-6751185` **未推、未删**（指向 2026-10-21 的
  docs 提交，是别的事后恢复点，不属本卡所有权；动它们要单独经用户确认）。
- 没有碰任何代码文件（本批只有 `CHANGELOG.md`、`AGENTS.md` 与证据目录）。

## 6. 判据对照（卡面「完成判据」逐条）

| 判据 | 读数 | 结论 |
|---|---|---|
| `git ls-remote --tags origin v1.1.0` 有且指向三绿的提交 | `refs/tags/v1.1.0^{}` = `49c3bed…`，即三条 success 的同一 head | ✅ |
| CHANGELOG 里 `[Unreleased]` 为空段、v1.1.0 段有日期 | `:11` 空段（只留一行搬空说明）；`:17` = `## [v1.1.0] - 2026-10-23` | ✅ |
| 不得出现强推或移动 tag | §5.1 | ✅ |
| S39.1 合并 + 去重 + 补 32/33 + 每个 hash 复核 | §2 表 + `s39_hash_audit.txt`（42 个全解析，0 失败；含一条挂错已更正） | ✅ |
| S39.2 版本行改 v1.1.0、"领先 N"归零并带锚 | AGENTS.md 版本块；不抄自指 sha 的理由见 §3 | ✅ |
| S39.3 提交→推送→同 head 三绿→打注释 tag→推 tag，证据记 sha 与三条 run id | §5 表 | ✅ |
| S39.4 发布后冒烟读 PASS 行 | `smoke:1141 结果：PASS=3 FAIL=0` | ✅ |
| D-V18-15 收口覆盖面 | 卡面 4 条三级任务 + 继承增量表（**无** STEP-39 行 ⇒ 零项）+ 卡面自身无增量节 ⇒ 全判 | ✅ |

## 7. 过程中的两条自我记录
1. 本卡的 CHANGELOG 手术是用脚本做的（34 行整段搬移不适合逐条手工替换）。
   第一版脚本有一个**会吃掉别的条目**的错：它按"第一条到第二条之间"做区间替换，
   而两条重复条目之间还夹着「角色门禁单参数化」那条——照旧执行会静默删掉一条发布说明。
   改成"删第二条 + 改第一条来源行"两步，并加了断言要求中间那条必须在位，才让它落盘。
   记在这里是因为这类错误**不报错**：文件照样是合法 markdown，只是少了一条。
2. `### Fixed` 这类标题在每个历史段都存在（全文件 9 次命中），
   所以任何"按标题定位"的脚本必须先框定窗口——第一版就是因此直接 assert 失败而没写盘（这次是响的）。
