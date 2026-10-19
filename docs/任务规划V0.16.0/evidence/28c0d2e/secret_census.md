# 敏感形门全仓普查（main@28c0d2e，新门 secret_scan_for_path，只记文件与条数）
命令：对 git ls-files 的每个可读文本文件调用 scripts/guards.py 的 secret_scan_for_path；.project/ 为第三方参考仓，不计入自有源码面。
files_with_hits_total 257 hits_total 644
own_source_files_with_hits 188（含 .project/）

## 自有源码面（排除 .project/）
1 apps/api/app/providers/reranker.py
6 apps/api/tests/test_auth.py
3 apps/api/tests/test_backchannel_logout.py
1 apps/api/tests/test_manifest_asset_alignment.py
1 apps/api/tests/test_manifest_state_machine.py
1 apps/api/tests/test_manifest_sync.py
11 apps/api/tests/test_provider_contract.py
4 apps/api/tests/test_provider_defects_p15_p17.py
3 apps/api/tests/test_push_providers.py
2 apps/api/tests/test_session_store_redis.py
1 apps/api/tests/test_w1_push_domain.py
合计 11 个自有文件
