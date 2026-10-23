#!/usr/bin/env python3
"""安全扫描步的执行体：跑一次，没产出报告就再跑一次；两次都没有 ⇒ 按「扫描器未运行」记。

为什么需要它（P-77）：`security.yml` 的四个扫描器步骤此前把"工具没跑成"与"跑成了但发现问题"
混在同一层 bash 里——下载抖动、pip 装不上、命令崩在半路，都只会让 verdict 文件停在
预先写好的 `SCANNER_ERROR` 上，人看不出是**这一次没跑成**还是**这个工具一直跑不成**。
而安全门的信用正取决于这两件事能不能一眼分开：把"没运行"报成"发现漏洞"，
下一次真出事时没人会信这条红。

三条判据，都做成可单测的纯函数 + 注入点：
1. **换不来了结论才算没跑成**：报告文件缺失或 0 字节 ⇒ 重试一次；两次都没报告 ⇒ scanner_error。
   "检出漏洞"（rc 非 0 但报告在）**不是**失败——裁决权在末尾的汇总门禁，这里只管工具命运。
2. **每一轮开始前删掉上一轮的报告**。不删就会有一种偏绿的假绿：第一轮崩在半路写了个残缺文件，
   第二轮根本没执行成功，门却读到了"报告存在"。
3. **重试次数是写死的两次**（`ATTEMPTS`），不是无限重试。无限重试会把"这个环境跑不成"
   伪装成"跑得慢"，而 30 分钟的 job 超时才是它真正的下场。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

ATTEMPTS = 2
RETRY_DELAY_S = 3.0

RAN = "ran"
SCANNER_ERROR = "scanner_error"


def report_state(report: Path) -> tuple[bool, int]:
    """(报告是否可用作"这一轮跑成了", 字节数)。0 字节与不存在同权：都换不来结论。"""
    if not report.is_file():
        return False, 0
    return report.stat().st_size > 0, report.stat().st_size


def run_scanner(
    name: str,
    cmd: list[str],
    report: Path,
    *,
    cwd: Path | None = None,
    attempts: int = ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
    runner: Callable[..., Any] = subprocess.run,
    env: dict[str, str] | None = None,
    status_file: Path | None = None,
) -> dict[str, Any]:
    """跑扫描器至多 `attempts` 次；返回 {"name","status","reason","last_rc","tries":[...]}。

    `runner` / `sleep` 是注入点：反证用例要把"命令永远不产出报告"和"两次都产出"这两发
    喂进来，还要断言第二次之前确实等过一次（不注入 sleep 的话，用例就只能真等三秒或假装）。
    `status_file`：把结论落成 JSON 给下一步读。gitleaks 用退出码区分"干净/检出/工具坏"，
    包一层重试之后那个码必须还能取回来，否则判据只能靠猜。
    """
    tries: list[dict[str, Any]] = []
    result: dict[str, Any]
    for attempt in range(1, attempts + 1):
        # 先删，再跑：本轮的判定只看本轮产出的字节数（判据 2）
        report.unlink(missing_ok=True)
        proc = runner(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True, env=env)
        produced, size = report_state(report)
        tries.append({"attempt": attempt, "rc": proc.returncode, "report_bytes": size})
        # 转发被包那一层的输出：不转的话 `capture_output=True` 会把工具自己的报错吞干净，
        # 而"为什么没产出报告"恰恰是唯一需要看的東西（console.log 因此仍是工具的原话）。
        for stream_name in ("stdout", "stderr"):
            text = str(getattr(proc, stream_name, "") or "")
            if text.strip():
                print(f"[{name}] {stream_name}（末 4000 字）：{text[-4000:]}", flush=True)
        print(
            f"[{name}] 第 {attempt}/{attempts} 次：rc={proc.returncode} 报告字节={size}"
            + ("" if produced else "（无报告 ⇒ 这一轮没跑出结论）"),
            flush=True,
        )
        if produced:
            rc_note = (
                "" if proc.returncode == 0
                else f"（rc={proc.returncode}：这是「扫描成功且发现问题」的形状，不是工具坏）"
            )
            print(f"[{name}] 判定=ran{rc_note}", flush=True)
            result = {"name": name, "status": RAN, "reason": "", "last_rc": proc.returncode, "tries": tries}
            break
        if attempt < attempts:
            print(f"[{name}] 没有报告 ⇒ {RETRY_DELAY_S}s 后重试一次", flush=True)
            sleep(RETRY_DELAY_S)
    else:
        # 两次都没有报告：原因必须写明"扫描器未运行"，不许写成"发现漏洞"或"没有漏洞"
        last_rc = tries[-1]["rc"] if tries else None
        result = {
            "name": name,
            "status": SCANNER_ERROR,
            "reason": (
                f"扫描器未运行：{name} 连试 {attempts} 次都没有产出报告文件（最后一轮 rc={last_rc}），"
                "本维**没有终判**——既不是「发现漏洞」也不是「没有漏洞」"
            ),
            "last_rc": last_rc,
            "tries": tries,
        }
        print(f"[{name}] 判定={SCANNER_ERROR} ⇒ {result['reason']}", flush=True)
    if status_file is not None:
        import json

        status_file.parent.mkdir(parents=True, exist_ok=True)
        status_file.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result


def main(argv: list[str]) -> int:
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            reconfigure = getattr(stream, "reconfigure", None)
            if reconfigure is None:
                continue
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001 编码只是体验问题，不该把扫描判据带崩
                pass
    parser = argparse.ArgumentParser(description="安全扫描步的重试与「未运行」判定")
    parser.add_argument("--name", required=True)
    parser.add_argument("--report", required=True, help="扫描器必须产出的报告文件（相对 --cwd）")
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--attempts", type=int, default=ATTEMPTS)
    parser.add_argument("--status-file", default="", help="把结论落成 JSON 给下一步读（可选）")
    parser.add_argument("cmd", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)

    cmd = list(args.cmd)
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    status_file = Path(args.status_file) if args.status_file else None
    if not cmd:
        # 没东西可跑也走同一条 status_file 通道：消费侧不必区分"我忘了传命令"与"工具跑不成"
        print(f"[{args.name}] 判定=scanner_error ⇒ 没给要执行的命令，没有东西可跑")
        if status_file is not None:
            import json

            status_file.parent.mkdir(parents=True, exist_ok=True)
            status_file.write_text(
                json.dumps({"name": args.name, "status": SCANNER_ERROR, "reason": "没有要执行的命令",
                            "last_rc": None, "tries": []}, ensure_ascii=False),
                encoding="utf-8",
            )
        return 1

    result = run_scanner(
        args.name,
        cmd,
        Path(args.report),
        cwd=Path(args.cwd),
        attempts=args.attempts,
        status_file=status_file,
    )
    return 0 if result["status"] == RAN else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
