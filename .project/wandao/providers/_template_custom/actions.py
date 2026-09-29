import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from wandao_logging import emit_legacy
    from wandao_report import finalize_report
except ModuleNotFoundError:
    def emit_legacy(provider, message, *, event="log.message", level="info", **fields):
        print(message, flush=True)
    def finalize_report(report, **_fields):
        return report


PROVIDER_ID = "your-custom-provider"


def emit(message, *, event="log.message", level="info", **fields):
    emit_legacy(PROVIDER_ID, message, event=event, level=level, **fields)


def print_result(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))


def login(args):
    emit("TODO: open browser, complete login, then save reusable credentials safely.", event="auth.started")
    print_result(
        {
            "provider": PROVIDER_ID,
            "mode": "login",
            "success": False,
            "message": "请在 actions.py 中实现真实登录逻辑。",
            "workspaceUrl": args.workspace_url,
        }
    )


def scan_toc(args):
    emit("TODO: fetch remote spaces, folders or documents from the target platform.", event="toc.scan.started")
    print_result(
        {
            "provider": PROVIDER_ID,
            "readOnly": True,
            "totalDocs": 0,
            "folderCount": 0,
            "nodes": [],
            "workspaceUrl": args.workspace_url,
        }
    )


def export(args):
    emit(
        "TODO: export selected documents and preserve Markdown, images and attachments.",
        event="task.started",
        totals={"documents": len(args.doc_id or [])},
        output=args.output,
        workspaceUrl=args.workspace_url,
    )
    emit(
        "TODO 导出完成，请在 actions.py 中实现真实导出逻辑。",
        event="task.completed",
        level="warn",
        stats={"exportedDocs": 0, "failureCount": 0},
    )
    print_result(
        finalize_report({
            "provider": PROVIDER_ID,
            "mode": "export",
            "totalDocs": len(args.doc_id or []),
            "exportedDocs": 0,
            "failureCount": 0,
            "failures": [],
            "output": args.output,
            "workspaceUrl": args.workspace_url,
        }, provider=PROVIDER_ID, mode="export", output=args.output)
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-url", required=True)
    parser.add_argument("--output", default="")
    parser.add_argument("--login", action="store_true")
    parser.add_argument("--scan-toc", action="store_true")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--doc-id", action="append")
    args = parser.parse_args()

    try:
        if args.login:
            login(args)
        elif args.scan_toc:
            scan_toc(args)
        elif args.export:
            export(args)
        else:
            raise SystemExit("Please pass --login, --scan-toc or --export")
    except Exception as exc:
        emit(
            f"任务失败：{exc}",
            event="task.failed",
            level="error",
            error={"type": type(exc).__name__, "message": str(exc)},
        )
        raise


if __name__ == "__main__":
    main()
