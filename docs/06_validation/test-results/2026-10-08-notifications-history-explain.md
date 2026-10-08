# R3.5 性能留证：notifications/history EXPLAIN（2026-10-08，隔离 PG bothot-s3-pg:5547）

## 方法
灌 5000 行模拟量级（sub='bench-user' 定向行）→ EXPLAIN ANALYZE → 删除基准数据。
对应端点：`GET /api/v1/system/notifications/history`（`apps/api/app/api/v1/system.py`）。

## 结果

### 定向查询（sub=me，单条件）
```
Index Scan Backward using ix_notifications_sub_created on notifications
  (cost=0.27..8.29 rows=1) (actual time=0.020..0.020 rows=0 loops=1)
  Index Cond: ((sub)::text = 'me'::text)
Execution Time: 0.034 ms
```
**结论：复合索引 `(sub, created_at)` 正向命中，Backward Index Scan 免排序。**

### OR 广播查询（sub='me' OR is_broadcast=true）
```
Sort (cost=79.46..79.82 rows=145) (actual time=0.359..0.359 rows=0 loops=1)
  Sort Key: created_at DESC
  -> Seq Scan on notifications (cost=0.00..75.60 rows=145) (actual time=0.340..0.341)
Execution Time: 0.380 ms
```
**结论：planner 对 OR 条件放弃复合索引（is_broadcast 无独立索引），5000 行量级
Seq Scan + Sort = 0.38ms，可接受。优化触发条件：notifications 行数达 10 万级或
广播占比显著——届时优先「UNION 两分支各自走索引」改写，其次 is_broadcast 部分索引。**
