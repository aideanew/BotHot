# 性能基线读数（tag=base，inject=0ms，n=50）

- GET /api/v1/spaces：p50=11.31ms / p95=13.18ms（n=50）
- GET /api/v1/hot/topics：p50=8.42ms / p95=10.49ms（n=50）
- GET /api/v1/jobs：p50=8.6ms / p95=17.31ms（n=50）
- GET /api/v1/hot/feed：p50=9.4ms / p95=10.7ms（n=50）
- ingest[short]：p50=29.15ms / p95=40.06ms（n=50）
- ingest[long]：p50=27.57ms / p95=32.8ms（n=50）
- first_token[recorded-replay]：p50=0.94ms / p95=2.03ms（n=50）
