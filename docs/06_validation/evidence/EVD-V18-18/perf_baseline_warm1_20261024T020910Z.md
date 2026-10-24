# 性能基线读数（tag=warm1，inject=0ms，n=50）

- GET /api/v1/spaces：p50=12.82ms / p95=15.59ms（n=50）
- GET /api/v1/hot/topics：p50=9.8ms / p95=11.82ms（n=50）
- GET /api/v1/jobs：p50=8.74ms / p95=10.13ms（n=50）
- GET /api/v1/hot/feed：p50=10.53ms / p95=11.46ms（n=50）
- ingest[short]：p50=29.34ms / p95=44.65ms（n=50）
- ingest[long]：p50=27.62ms / p95=33.22ms（n=50）
- first_token[recorded-replay]：p50=0.92ms / p95=1.58ms（n=50）
