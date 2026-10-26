S54.1 先红与"修之前的库内现状"（@win，便携 PG16.15@5547 的 bothot_test，**未重建、未手工删行**）

一、连跑两次 `pytest tests/test_scheduler.py -q`（同一库，间隔 0）
  round1 rc=1：1 failed, 24 passed in 12.51s
  round2 rc=1：1 failed, 24 passed in 12.51s（与 round1 逐字同形 ⇒ 稳定红，不是时序抖动）
  红因（两轮同一条）：
    psycopg.errors.UniqueViolation: duplicate key value violates unique constraint "users_pkey"
    DETAIL:  Key (id)=(u-s35-daily) already exists.
    [SQL: INSERT INTO users (id, sub, email, nickname, status, role) VALUES (...)]
    参数就是本用例自己写死的夹具值（id=u-s35-daily / sub=sub-s35-daily），原文见
    s54_1_round1_red.txt 与 s54_1_round2_red.txt（两份都在本目录）。
    ⇒ P-120 的直接复现：**上一跑留下的这行用户让本用例进门就撞主键**；
      与"第二次才红"的原始描述相比，本机现状是**首跑即红**——因为这张库已经被
      STEP-49/50/51/52 多个会话的全量跑用过，残留至少跨了 4 次会话。

二、修之前库里到底剩了什么（临时脚本现读，脚本不入库）
  users 残留行：1 条，主键与 sub 就是上面那对夹具值。
  jobs 残留：2 条
    - daily_report / 幂等戳 daily_report:2026-10-25 / 状态 SUCCEEDED
    - hot_cluster  / 幂等戳 hot_cluster:2026-10-26:1 / 状态 QUEUED
  这两条 Job 的 job_items 行数：0
  读数要点（这是本卡判据里最容易被读错的一处）：
    · daily_report 那条日期是 **10-25**：来自更早某次成功跑完后没清干净的每日入队；
    · hot_cluster 那条戳里的日期是 **10-26（当天，真实墙钟）**，而 `test_scheduler` 的
      每日用例用的是冻结时钟（断言写死 10-24 那一族）⇒ **这条不是每日用例产的**，
      它是 `test_w2_worker.py::test_hot_cluster_job_consumed_by_worker` 自己建的作业
      （该用例在 STEP-52 后端基线那一跑里红了，红在 `actual=QUEUED`，
      失败即退出 ⇒ 它自己的清场没执行 ⇒ 给下一跑留了一条 QUEUED 的同型作业）。
    · 于是 P-120 裁定行"残留 daily_report 被 w2_worker 吃走"这条链，在今天的读数上
      要修正一半：w2 的残留**主要是它自己的**，每日用例的残留是另一条独立的同族污染。
      修法不变（进门先清 + 出门必清），但"修完 w2 就绿"这个期望必须由连跑读数来判，
      不能当推论写进结论——见 S54.3。
