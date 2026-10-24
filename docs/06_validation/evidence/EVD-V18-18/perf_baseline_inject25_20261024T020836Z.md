# 性能基线读数（tag=inject25，inject=25ms，n=50）

- GET /api/v1/spaces：p50=48.65ms / p95=53.47ms（n=50）
- GET /api/v1/hot/topics：p50=37.59ms / p95=52.72ms（n=50）
- GET /api/v1/jobs：p50=34.5ms / p95=50.77ms（n=50）
- GET /api/v1/hot/feed：p50=35.86ms / p95=51.76ms（n=50）
- ingest[short]：p50=50.07ms / p95=62.65ms（n=50）
- ingest[long]：p50=62.23ms / p95=68.49ms（n=50）
- first_token[recorded-replay]：p50=33.06ms / p95=39.71ms（n=50）
