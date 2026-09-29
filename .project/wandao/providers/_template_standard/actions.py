import argparse
import json
import shutil
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


PROVIDER_ID = "your-provider"


def emit(message, *, event="log.message", level="info", **fields):
    emit_legacy(PROVIDER_ID, message, event=event, level=level, **fields)


def print_result(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))


def iter_markdown_files(source_dir):
    for path in sorted(source_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".md", ".markdown"}:
            yield path


def posix_rel(path, root):
    return path.relative_to(root).as_posix()


def build_nodes(source_dir):
    nodes = []
    seen_folders = set()
    for md_file in iter_markdown_files(source_dir):
        rel = posix_rel(md_file, source_dir)
        parent_id = ""
        parent = md_file.parent
        if parent != source_dir:
            parts = Path(posix_rel(parent, source_dir)).parts
            current = Path()
            for part in parts:
                current = current / part
                folder_key = current.as_posix()
                folder_id = f"folder:{folder_key}"
                if folder_id not in seen_folders:
                    folder_parent = "" if current.parent == Path(".") else f"folder:{current.parent.as_posix()}"
                    nodes.append(
                        {
                            "nodeId": folder_id,
                            "exportId": "",
                            "title": part,
                            "parentNodeId": folder_parent,
                            "selectable": False,
                        }
                    )
                    seen_folders.add(folder_id)
                parent_id = folder_id
        nodes.append(
            {
                "nodeId": f"doc:{rel}",
                "exportId": rel,
                "title": md_file.stem,
                "parentNodeId": parent_id,
                "selectable": True,
            }
        )
    return nodes


def scan(args):
    source_dir = Path(args.source_dir).expanduser().resolve()
    if not source_dir.exists():
        raise SystemExit(f"Source directory does not exist: {source_dir}")
    nodes = build_nodes(source_dir)
    print(
        json.dumps(
            {
                "provider": "your-provider",
                "readOnly": True,
                "totalDocs": sum(1 for node in nodes if node.get("selectable")),
                "folderCount": sum(1 for node in nodes if not node.get("selectable")),
                "nodes": nodes,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def export(args):
    source_dir = Path(args.source_dir).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve()
    if not source_dir.exists():
        raise SystemExit(f"Source directory does not exist: {source_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    all_docs = list(iter_markdown_files(source_dir))
    selected = set(args.doc_id or [])
    docs = [path for path in all_docs if not selected or posix_rel(path, source_dir) in selected]
    exported = 0
    skipped = 0
    failures = []
    emit(
        f"开始导出 {PROVIDER_ID}：共 {len(docs)} 篇。",
        event="task.started",
        totals={"documents": len(docs)},
        output=str(output_dir),
        sourceDir=str(source_dir),
    )

    for index, md_file in enumerate(docs, 1):
        rel = posix_rel(md_file, source_dir)
        target = output_dir / rel
        try:
            emit(
                f"开始导出文档：{rel}",
                event="document.export.started",
                doc={"path": rel, "index": index},
            )
            if args.incremental and target.exists():
                skipped += 1
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(md_file, target)
                exported += 1
            emit(
                f"文档处理完成：{rel}",
                event="document.export.completed",
                doc={"path": rel, "index": index, "output": str(target)},
            )
        except Exception as exc:
            failures.append({"docId": rel, "error": str(exc)})
            emit(
                f"文档导出失败：{rel}：{exc}",
                event="document.export.failed",
                level="error",
                doc={"path": rel, "index": index},
                error={"type": type(exc).__name__, "message": str(exc)},
            )
        emit(
            f"progress {index}/{len(docs)} exported={exported} skipped={skipped} failures={len(failures)}",
            event="task.progress",
            progress={"current": index, "total": len(docs)},
            stats={"exportedDocs": exported, "skippedDocs": skipped, "failureCount": len(failures)},
        )

    result = {
        "provider": PROVIDER_ID,
        "mode": "export",
        "totalDocs": len(docs),
        "exportedDocs": exported,
        "skippedDocs": skipped,
        "failureCount": len(failures),
        "failures": failures,
        "output": str(output_dir),
    }
    emit(
        "导出完成" if not failures else f"导出完成，但有 {len(failures)} 个失败项",
        event="task.completed",
        level="success" if not failures else "warn",
        stats={"exportedDocs": exported, "skippedDocs": skipped, "failureCount": len(failures)},
    )
    print_result(finalize_report(result, provider=PROVIDER_ID, mode="export", output=output_dir))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--output", default="")
    parser.add_argument("--scan-toc", action="store_true")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--doc-id", action="append")
    parser.add_argument("--incremental", action="store_true")
    args = parser.parse_args()

    try:
        if args.scan_toc:
            scan(args)
        elif args.export:
            if not args.output:
                raise SystemExit("--output is required for export")
            export(args)
        else:
            raise SystemExit("Please pass --scan-toc or --export")
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
