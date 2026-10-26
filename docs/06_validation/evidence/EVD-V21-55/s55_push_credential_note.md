推送凭据的实测口径（不抄上一版的说法）
======================================

2026-10-26 20:12，`4a2c62b` 推 origin/main。驱动 `push_s55.sh` + `write_cred.py`（会话临时目录，不入库）。

逐字读数（驱动打印的那两行，token 值不回显）：

```
cred_file_written exists=True mode_digits=0o666 mode_is_600=False bytes=122
push_rc=0
cred_exists_after_rm=NO
```

三件必须如实说的：

1. **`mode_is_600=False`，实测 0o666。** 我用 `os.open(..., 0o600)` 创建，`stat` 仍报 0o666——
   这台机器上 git-bash/Windows 的 st_mode 只有"可读/只读"两态，POSIX 位不代表真实权限，
   真正管用的是 NTFS ACL。所以：**"临时凭据文件 mode 600"这句话在本平台上是无法兑现的表述**，
   STEP-54 收口批与 07 记录里那句"临时文件 mode 600"按今天的读数要算**不准确**（当时的做法与现在相同：
   进程内取内嵌 PAT、写完立刻在同一条命令里 `rm -f` 并核实）。这一条不靠改历史文本掩盖，
   而是在这里记下现值，后续推送沿用同一流水并保留这份读数。
   真正可复用的降低风险手段是"存在时间"而不是"模式位"：文件在同一条脚本内创建→使用→删除，
   `cred_exists_after_rm=NO` 是删后核实，存活约 2 秒。
   下一次若要更进一步，可改用 `GIT_ASKPASS` 指一个"运行时现取内嵌 PAT 再打印"的脚本——
   磁盘上就不再有承载 token 的文件（本卡不动这套流水，只把选项写清楚，别让它下次靠猜）。
2. **`fatal: User cancelled dialog.` 不是推送失败。** 它是 GCM 在 `credential.interactive=false` 下
   拿不到凭据时打到 stderr 的噪音；随后 store helper 用临时文件命中，`push_rc=0` 且有
   `e4a9a67..4a2c62b  main -> main` 的引用更新行。只看 rc 会过，只看这句 fatal 会误判——
   所以判据是"rc=0 且引用行存在且事后 `origin/main...HEAD` 为 `0 0`"，三条都在。
3. **远端 URL 未被动过**：`git remote -v` 两行都不含凭据；推送用 `-c credential.helper="store --file=…"`
   逐次传参，不写配置。凭据值从未出现在聊天、日志、文件名或本文件里（本文件只写 16 位 sha 与字节数）。
