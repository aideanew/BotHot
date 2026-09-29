import argparse
import json
import re
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


PROVIDER_ID = "your-import-provider"
RESOURCE_PATTERN = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def emit(message, *, event="log.message", level="info", **fields):
    emit_legacy(PROVIDER_ID, message, event=event, level=level, **fields)


def print_result(data):
    print(json.dumps(data, ensure_ascii=False, indent=2), flush=True)


def iter_markdown_files(source_dir):
    for path in sorted(source_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".md", ".markdown"}:
            yield path


def posix_rel(path, root):
    return path.relative_to(root).as_posix()


def inside(root, path):
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def build_nodes(source_dir):
    nodes = []
    seen_folders = set()
    for md_file in iter_markdown_files(source_dir):
        rel = posix_rel(md_file, source_dir)
        parent_id = ""
        parent = md_file.parent
        if parent != source_dir:
            current = Path()
            for part in Path(posix_rel(parent, source_dir)).parts:
                current = current / part
                folder_id = f"folder:{current.as_posix()}"
                if folder_id not in seen_folders:
                    folder_parent = "" if current.parent == Path(".") else f"folder:{current.parent.as_posix()}"
                    nodes.append({"nodeId": folder_id, "exportId": "", "title": part, "parentNodeId": folder_parent, "selectable": False})
                    seen_folders.add(folder_id)
                parent_id = folder_id
        nodes.append({"nodeId": f"doc:{rel}", "exportId": rel, "title": md_file.stem, "parentNodeId": parent_id, "selectable": True})
    return nodes


def referenced_resources(md_file, source_dir):
    text = md_file.read_text(encoding="utf-8", errors="ignore")
    resources = []
    for match in RESOURCE_PATTERN.finditer(text):
        raw = match.group(1).split()[0].strip("<>'\"")
        if not raw or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", raw) or raw.startswith("#"):
            continue
        resource = (md_file.parent / raw).resolve()
        if resource.exists() and resource.is_file() and inside(source_dir, resource):
            resources.append(resource)
    return resources


def scan_source(args):
    source_dir = Path(args.source_dir).expanduser().resolve()
    if not source_dir.exists():
        raise SystemExit(f"Source directory does not exist: {source_dir}")
    nodes = build_nodes(source_dir)
    print_result(
        {
            "provider": PROVIDER_ID,
            "readOnly": True,
            "sourceDir": str(source_dir),
            "totalDocs": sum(1 for node in nodes if node.get("selectable")),
            "folderCount": sum(1 for node in nodes if not node.get("selectable")),
            "nodes": nodes,
        }
    )


def import_docs(args):
    source_dir = Path(args.source_dir).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve()
    if not source_dir.exists():
        raise SystemExit(f"Source directory does not exist: {source_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    selected = set(args.doc_id or [])
    all_docs = list(iter_markdown_files(source_dir))
    docs = [path for path in all_docs if not selected or posix_rel(path, source_dir) in selected]
    imported = 0
    skipped = 0
    resource_uploads = 0
    failures = []
    imported_items = []

    emit(f"开始导入 {PROVIDER_ID}：共 {len(docs)} 篇。", event="task.started", totals={"documents": len(docs)}, sourceDir=str(source_dir), output=str(output_dir))
    for index, md_file in enumerate(docs, start=1):
        rel = posix_rel(md_file, source_dir)
        target = output_dir / rel
        try:
            if args.incremental and target.exists():
                skipped += 1
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(md_file, target)
                imported += 1
                imported_items.append({"relativePath": rel, "target": str(target)})
                if args.copy_resources:
                    for resource in referenced_resources(md_file, source_dir):
                        resource_target = output_dir / posix_rel(resource, source_dir)
                        resource_target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(resource, resource_target)
                        resource_uploads += 1
            emit(f"导入完成：{rel}", event="document.import.completed", doc={"path": rel, "index": index})
        except Exception as exc:
            failures.append({"relativePath": rel, "error": str(exc)})
            emit(f"导入失败：{rel}：{exc}", event="document.import.failed", level="error", doc={"path": rel, "index": index}, error={"type": type(exc).__name__, "message": str(exc)})
        print(f"progress {index}/{len(docs)} imported={imported} skipped={skipped} failures={len(failures)}", flush=True)
        emit(
            f"进度 {index}/{len(docs)}",
            event="task.progress",
            progress={"current": index, "total": len(docs)},
            stats={"importedDocs": imported, "skippedDocs": skipped, "failureCount": len(failures), "attachmentSuccess": resource_uploads},
        )

    report_path = output_dir / "00-导入报告.json"
    report = finalize_report(
        {
            "provider": PROVIDER_ID,
            "mode": "import",
            "sourceDir": str(source_dir),
            "output": str(output_dir),
            "totalDocs": len(docs),
            "importedDocs": imported,
            "skippedDocs": skipped,
            "failureCount": len(failures),
            "attachmentSuccess": resource_uploads,
            "imported": imported_items,
            "failures": failures,
        },
        provider=PROVIDER_ID,
        mode="import",
        report_file=report_path,
        output=output_dir,
    )
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    emit(
        "导入完成" if not failures else f"导入完成，但有 {len(failures)} 个失败项",
        event="task.completed",
        level="success" if not failures else "warn",
        reportFile=str(report_path),
        stats={"importedDocs": imported, "skippedDocs": skipped, "failureCount": len(failures), "attachmentSuccess": resource_uploads},
    )
    print_result(report)


def parse_args(argv):
    parser = argparse.ArgumentParser(description="标准导入 Provider 模板")
    parser.add_argument("--scan-source", action="store_true")
    parser.add_argument("--import", dest="do_import", action="store_true")
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--output", default="")
    parser.add_argument("--doc-id", action="append", default=[])
    parser.add_argument("--copy-resources", action="store_true")
    parser.add_argument("--incremental", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    if args.scan_source:
        scan_source(args)
        return 0
    if args.do_import:
        if not args.output:
            raise SystemExit("--import requires --output")
        import_docs(args)
        return 0
    raise SystemExit("请指定 --scan-source 或 --import")


if __name__ == "__main__":
    raise SystemExit(main())
