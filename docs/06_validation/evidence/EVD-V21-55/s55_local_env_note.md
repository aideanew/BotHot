本机环境事故与处置（写在这里，因为最终那跑的读数要能被归因）
==============================================================

2026-10-26 19:23～19:31（Asia/Shanghai），@win。

事实链（每条都有现取读数）：

1. 19:23:55 我按 CI 顺序启动最终门链（`chain3.sh`）。前两步绿：`rc_ruff=0`、`rc_mypy=0`
   （原文已在 `s55_local_gates_pass2.txt` 之后的这次尝试里，因链被弃而未归档，读数见下面第 3 条）。
2. 第三步 `alembic upgrade head` **挂住**（4 分半无输出）。现取诊断：`netstat -ano | grep :5547` 零命中、
   `Get-Process postgres` 零命中 ⇒ **本机自备便携 PG16@5547 根本没在跑**（它上一次写日志是 14:50:30，
   之后随会话中断一起没了；`data/postmaster.pid` 是 10-24 09:41 的遗留文件）。
   用 SQLAlchemy 直连也复现：`psycopg.errors.ConnectionTimeout`（::1 与 127.0.0.1 两次尝试都超时）。
3. 我停掉这条链（`TaskStop`），然后按 `docs/任务规划V0.21.0/04-剩余可执行大纲体系.md` §五 第 195 行的
   自备库口径把它启回来：`%USERPROFILE%\pg16-5547\pgdist\bin\pg_ctl.exe -D %USERPROFILE%\pg16-5547\data start`。
   - 第一次我用 `-o "-p 5547 -h 127.0.0.1"` 起 ⇒ 只监听 IPv4，而 DSN 写的是 `localhost`，
     于是**每次连接先试 ::1 超时再回落**，实测首连 5.47s。这是我起法不对，不是库的问题。
   - 对照旧日志（`pg16-5547/logfile` 里 10-24 09:41 那两行 `listening on IPv6 address "::1"` /
     `IPv4 127.0.0.1`）确认原启动面同时监听两个回环 ⇒ 改用 `-o "-p 5547 -h localhost"` 重启，
     新日志同样出现两行 listening，稳态 `localhost` 连接 0.45s（首连 4.2s 是 DNS 冷缓存，一次性的）。
4. 库内现状核实（不是"我以为起来了"）：`select version_num from alembic_version` ⇒ `ab1006c2a`（单头、
   与 HEAD 一致），public 表 25 张，`select count(*) from jobs` ⇒ **0 行**
   （STEP-54 的"出门必清"在这次重启后仍然成立，说明它的 finally 清场是真的）。
5. 被停掉的那条链留下一个**孤儿 pytest**（`-q -rs --cov=app --cov-report=json`，19:28:33 起），
   它跑在没有数据库的时段上——那份读数如果用会是假绿/假红的混合体。我按 PID 核实命令行后把这一对
   进程（10960 与其 shim 6188）停掉，`Get-Process python` 归零，然后删除半途的 `gates3.txt` 重跑。
   ⇒ 所以本目录归档的门链里没有那次尝试；被弃的原因写在这里，不靠"读数没写就是没跑"。
6. **我自己重跑时又造出第二条链**（这一条更要记）：`TaskStop` 只杀了外层包装 bash，
   内层 `chain3.sh`（PID 8100）继续跑；我从 19:31 又起一条（PID 15288）写**同一个** `gates3.txt`，
   于是文件里出现"pytest 才 5% 却已经有 rc_build=0"这种不可能的顺序——单看内容发现不了，
   是它自相矛盾才暴露。处置：`taskkill //PID 8100 //T //F` 与 `//PID 15288 //T //F` 两棵树全杀，
   `Get-Process python` 归零后删掉污染文件，改起**带两道自锁**的 `chain4.sh`（→ `gates4.txt`）：
   ① 起链前数一遍正在跑的脚本实例（>1 就 ABORT，且只数真正的脚本进程、不被 `-c eval` 包装误计），
   ② 起链前 `netstat` 确认 5547 在监听（不在就 ABORT，别再让 alembic 挂成"看起来像测试"的连接超时）。
   最终归档的门链是 `s55_local_gates_final.txt`（chain4 的原文），中间这两条被弃的链都不算证据。

对结论的影响：本次事故不改判据、不改代码，只改**归因**——最终那跑（`s55_local_gates_final.txt`）
必须在库起来之后取，否则 `AIDEANBOT_TEST_PG_DSN` 指空会连坐 skip 数（`SKIP_BASELINE_WIN=692` 是零余量账，
PG 不可达会让连库用例整体挪进 skip 家族，读数就不可比）。
另外这也印证一条纪律：本机门链开跑前先 `netstat` 看 5547 有没有监听，别把"起不来的连接"跑成"看着像测试的超时"。
