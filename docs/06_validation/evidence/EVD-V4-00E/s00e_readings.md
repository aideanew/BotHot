# EVD-V4-00E — 验收环境供给与固定：本机现状测量与 `@ci` 读数

采集机：`@win`（Windows 10.0.19045 / Git Bash / `apps/api/.venv` Python 3.12）
基线：`main@a3ad07a`（本机 `db7e63b..a3ad07a` 两次推送之间完成）
依据：D-V4-01 签字注记（**正式验收面 = CI ubuntu-latest**；Win10 本地读数只算开发烟测）、
D-12（端口铁律）、D-V6-02（引用必须带 run id + head_sha + 结论）

## 1. S00E.1.1 现状测量（2026-10-17 22:1x，本机现跑，不是引用上一版）

```
$ python -c "import shutil; print(shutil.which('docker'), shutil.which('docker-compose'), shutil.which('wsl.exe'))"
None None C:\Windows\System32\wsl.exe
$ docker --version                 → FileNotFoundError（WinError 2）
$ wsl.exe --list --quiet           → rc=1，输出是 wsl.exe 的用法帮助（UTF-16 乱码）⇒ 无已装发行版
$ netstat -ano | grep LISTENING | grep -E "5433|6380"   → 无输出（两个部署端口都空着）
```

**结论**：本机**不能**供给验收环境（无 Docker、无 WSL 发行版、无 PG、无 Redis）。
所以本卡的 1.2 / 1.3（compose 起法与 `verify-backend` 串联）在本机**只能改文件、不能出读数**，
按 D-V4-01 那就不算验收；本卡真正能在本机闭合的只有 1.1（现状测量）、1.4（取 `@ci` 读数）、
2.2（文档三条纪律）。这条判断本身是这条卡现在最有用的产出——它把"00E 等 00H"这句话
变成了"00E 的验收面根本不在本机"。

## 2. S00E.1.4 / S00E.1.4.1 全量读数（`@ci` ubuntu，run **39041150287** @ `a3ad07a`）

| 卡面判据 | 实测 | 判定 |
|---|---|---|
| `failed = 0` | `1570 passed, 6 skipped, 1 warning in 103.15s` | 通过 |
| `skip ≤ 6` | `total_skipped=6 baseline=6` ⇒ **贴死上界** | 通过（见 §3 的口径提醒） |
| 覆盖率 | `Total coverage: 86.01%`（CI 的 `--cov-fail-under` 是 75） | 通过；85% 那条卡面数值仍无闸（EVD-V13-00H §7.4） |
| 点名那条缓存回归用例 | skip 列表六条是 `test_chat_sse:1130/1208`、`test_env_isolation:77`、`test_session_store_redis:47/71`、`test_we_notifications:247`；**`test_be02_engine_routing::test_short_link_second_ingest_hits_cache_via_url_fallback` 不在其中** ⇒ 它在真库上实跑 | 通过（R0 那条"出现即未验收"的判据成立） |
| `pg_unreachable` | 门禁自己打的是 `pg_unreachable=0` | 通过 ⇒ 这轮**没有**任何连库用例被静默 skip |

取数命令（REST 原始 zip，per-job 日志端点对本 token 返 403）：
`GET /repos/aideanew/BotHot/actions/runs/39041150287/logs` → 成员 `1_backend.txt`。

## 3. 本轮把"skip ≤ 6"用满之后暴露的口径问题（登记，不顺手改）

`SKIP_BASELINE`（ubuntu）与 `SKIP_BASELINE_WIN` 现在是同一个机制的两个实例，
前者 6 已**恰好被用满**。含义：任何新增的 LangBot/Redis 类 skip（例如新写一条真 Redis 转发用例）
都会把 ubuntu 的门顶红，而那张卡的作者会看到"CI 红了"却不一定知道这是**设计要求重测**，
而不是回归。00H 那条门今天已经在我自己身上验证过两次（441→443→444，见 EVD-V13-00H §8/§9），
所以这条不是猜测。程序已写在 `docs/04_engineering/cross-platform.md` §8，
本卡建议把它提升为**所有 skip 阈值共用的纪律**（写进 `conventions.md`，见 §4）。

## 4. S00E.1.2 的两处"卡面 vs 现读"冲突（按现读记录，不改代码去凑卡）

| # | 卡面要求 | 现读 | 处置 |
|---|---|---|---|
| E-1 | 新建 `docker/compose.test.yml` | 仓库里是 `docker/compose.ci.yml` + `docker/compose.yml`，CI 的 e2e 步用的是 `-f docker/compose.yml -f docker/compose.ci.yml`（`ci.yml:409-418`），**语义是"CI 覆盖层"而不是"测试专用栈"**；`scripts/test-env.sh` 则自带容器名/镜像（`bothot-test-pg`、`postgres:16-alpine`），不起 compose 文件 | 不新增第三个 compose 文件去对齐心名——那会让"测试环境"出现两套真相。要么把 `test-env.sh` 的实现改成吃 `compose.test.yml`（需 docker 才能验，本机判不了），要么按现读改卡。**待依赖机或规划方定** |
| E-2 | 测试宿主端口"用项目分配段（PG 5433、Redis 6380）" | `scripts/test-env.sh:37` 写死 `FORBIDDEN_PORTS=("5433" "5435" "6379" "6380")`，且 `guard_ports()` 命中即**拒绝启动**，注释给出的理由是 D-12：conftest 曾把部署库当测试库 | **不改脚本**。这条比卡面有力（它是一条事故规则），且 `conftest.py` 现在按 `AIDEANBOT_TEST_PG_DSN` 走独立库。卡面那句应改为"测试端口必须**避开**部署段，被占用时报错并点名占用者" |
| E-3 | S00E.1.2.1"端口被占时报错并点名占用者" | `guard_ports()` 只判"是否命中禁用端口"，**没有**"端口已被第三方占用"的检测（脚本里搜不到占用者探测）；`up` 路径也没有健康等待/超时的显式实现 | 这是 00E 剩下唯一真正的实现缺口。它需要 docker 才能验证（占用探测在 Linux 用 `ss -ltnp` / Windows 用 `netstat -ano` 可行，但"起来了没"必须靠容器），**本机判不了 ⇒ 不写不可证的代码**，留依赖机 |

## 5. S00E.3.2（同一命令连跑两次读数一致）——本机的替代证据与不足

本机跑不了带库的 `make verify-backend`（无 docker），所以做不到"同一命令在验收环境连跑两次"。
能给的替代证据是**跨机同命令复现**：同一 `10c1019`、同一条 pytest 命令，
`@ci` Windows runner `1098/441/0（987.74s）` 与本机 `@win` `1098/441/0（1038.71s）`
**逐项相同**（EVD-V5-00X 补记 3、EVD-V13-00H §7.3）。这证的是"读数不随机器漂移"，
但**不等于** S00E.3.2 要的"同一环境连跑两次不漂"——那条仍**待依赖机**。

## 6. 一条本批实测到的取证事实（影响所有下游引用）

一次 push 带多个提交时，GitHub **只为尖端提交建 workflow run**：`b751564`（与 `f7a3a6b` 同批推送）
在三个工作流里都没有任何 run（不是 cancelled；`ci-windows.yml` 没有 `concurrency` 组）。
所以引用"run X 证明提交 Y"之前必须核对 run 的 `head_sha == Y`。
本卡与 00H 的两次阈值收紧因此都改成**单独推送**，各自拿一条自己的 run。
