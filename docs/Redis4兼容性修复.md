# Redis 4 兼容性修复

## 问题

Redis 4 不支持 `HELLO` 命令（RESP3 协议握手），而 `redis-py` 的 asyncio 客户端默认尝试 RESP3 协商，导致：

```
redis.exceptions.ResponseError: unknown command `HELLO`, with args beginning with: `3`, 
```

## 影响

- 限流计数器无法使用 Redis → fail-open（不限流）
- 会话存储无法使用 Redis → 只能用 memory 模式
- 站内通知 pub/sub 无法工作

## 修复

在所有 `aioredis.from_url()` 调用中添加 `protocol=2` 参数，强制使用 RESP2 协议：

```python
# 修复前
client = aioredis.from_url(url)

# 修复后
client = aioredis.from_url(url, protocol=2)
```

## 修改文件

| 文件 | 说明 |
|------|------|
| `app/core/security.py` | 限流共享 Redis 客户端 |
| `app/core/cache.py` | 缓存 Redis 客户端 |
| `app/api/v1/auth.py` | 会话存储 Redis 客户端 |
| `app/api/v1/system.py` | 站内通知 Redis 客户端（2处） |

## 验证

修复后 Redis 连接正常，限流功能恢复（不再 fail-open 警告）。
