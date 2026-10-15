# 交接口径：本卡没做的、越界的、以及下一张卡该接的

## 1. 越界自报（判据 6 的诚实版本）

- `593dc5b`：11 条路径**全部**在卡面"允许修改"里（验证者以 `git show --name-status` 逐条比过）。
- `e7e9f25`：另加 `docs/任务规划V0.12.0/08-执行过程-独立执行段.md`（新）与
  `05-风险自检与局限.md`（改），**不在卡面允许清单**。依据是用户本轮指令
  "在 `docs/` 目录的最新任务规划目录下，新建一个文件记录执行过程"——指令授权 ≠ 卡面授权，
  所以这里记为"有出处的越界"而不是"合规"。本卡的记录文件因此也带这次提交。
- `docs/04_engineering/conventions.md:119` 我一度改成 `CI-Windows` 口径，随后**自行还原**：
  该文件不在卡面清单里，验证者也是建议"下一张卡的允许路径里再改"。
  待改文本（原句 `CI 的 \`windows-dev\` job 会跑它。`）：

  > `CI-Windows` 工作流的「entry.py 与 Makefile 目标面一致性」步会跑它
  > （STEP-00W D-V7-01 之后 `windows-dev` 已从 `CI` 工作流拆出，`CI` 只含 ubuntu 五 job）。

  现在这句话是**已知过期**的，读到 `conventions.md` 的人请以 `readings_ci_close.md` 为准。

## 2. 一次安全违反（凭据以明文出现在命令行）

取 `@ci` 读数时，我有一次把凭据字符串**直接写进 curl 的 `-H "Authorization: Bearer …"`**，
该命令行进入了会话记录。事后那次请求返回 `401 Bad credentials`，且与凭据管理器里可用的
那把（93 位）不是同一个值——但不能据此主张"没有暴露"。正确做法（本轮其余所有请求都用它，
值不回显）：

```bash
PAT=$(printf 'protocol=https\nhost=github.com\n\n' | git credential fill 2>/dev/null \
      | tr -d '\r' | sed -n 's/^password=//p')
```

处置：已向用户上报（建议按可暴露处理、按需轮换）；本目录所有入档文件里**没有**任何凭据值，
Actions 日志取回时 token 已被 GitHub 自身打成 `***`。

## 3. 下一张卡该接的三件

| 项 | 该做什么 | 归属建议 |
|---|---|---|
| U-23 | Windows 全量 pytest 仍 ~20min 不出结果。栈已定位到 **同步 `TestClient` 等 anyio blocking portal**（`starlette/testclient.py:351 → anyio/from_thread.py:340 → Future.result`，portal 线程停在 `selectors._select`），与 psycopg/启动探测无关。做法：`-v` 跑一次拿到用例名，再 `--timeout=60 -k` 二分；怀疑 `pytest-asyncio` 与 Windows Selector 循环的组合，或 TestClient 在 `asyncio.run` 外层的使用方式 | STEP-00R/新增 STEP-00W2（测试域） |
| 判据 4 的"最终 success" | `CI-Windows` 现为 failure（带栈）。00W 的"去遮蔽"目标已经达成（`CI` 结论独立为 success），但 windows 面要真绿必须先解 U-23 | 同上 |
| `pytest-timeout` 进 `uv.lock` | 现在只在 `pyproject.toml` 的 dev extra；`uv.lock` 未记（U-19 一并处理，CI 走 pip 不受影响） | U-19 |

## 4. 本机环境的两条硬事实（省下一位读者的时间）

- `docker` 不在 PATH（`docker: command not found`）⇒ 本卡判据 1 要求的 `@linux` 手跑面在
  这台 Win10 上拿不到，只能等 @ci 或换机。
- 本机回环 `127.0.0.1:1` / `:5` 的 `connect` **不产生 RST**（2.0s 超时），
  所以"秒拒地址"这类对照在本机造不出来（见 `mutation_proofs_probe_test.md` §3.1）。
