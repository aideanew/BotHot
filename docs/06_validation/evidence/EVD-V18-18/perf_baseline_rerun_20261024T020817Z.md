# 性能基线读数（tag=rerun，inject=0ms，n=50）

- GET /api/v1/spaces：p50=8.08ms / p95=10.6ms（n=50）
- GET /api/v1/hot/topics：p50=5.41ms / p95=8.27ms（n=50）
- GET /api/v1/jobs：p50=5.69ms / p95=8.37ms（n=50）
- GET /api/v1/hot/feed：p50=6.15ms / p95=8.62ms（n=50）
- ingest[short]：p50=27.85ms / p95=38.16ms（n=50）
- ingest[long]：p50=29.95ms / p95=34.16ms（n=50）
- first_token[recorded-replay]：p50=0.96ms / p95=1.77ms（n=50）
