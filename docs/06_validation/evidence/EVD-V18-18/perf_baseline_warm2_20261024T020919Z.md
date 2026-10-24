# 性能基线读数（tag=warm2，inject=0ms，n=50）

- GET /api/v1/spaces：p50=11.17ms / p95=12.39ms（n=50）
- GET /api/v1/hot/topics：p50=9.31ms / p95=10.96ms（n=50）
- GET /api/v1/jobs：p50=8.69ms / p95=10.11ms（n=50）
- GET /api/v1/hot/feed：p50=12.74ms / p95=21.13ms（n=50）
- ingest[short]：p50=29.34ms / p95=42.21ms（n=50）
- ingest[long]：p50=26.67ms / p95=32.36ms（n=50）
- first_token[recorded-replay]：p50=0.92ms / p95=2.21ms（n=50）
