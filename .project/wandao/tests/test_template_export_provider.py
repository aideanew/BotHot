import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_SCRIPT = REPO_ROOT / "providers" / "_template_standard" / "actions.py"


def parse_last_json(stdout: str) -> dict:
    decoder = json.JSONDecoder()
    for index, char in enumerate(stdout):
        if char != "{":
            continue
        try:
            data, end = decoder.raw_decode(stdout[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and not stdout[index + end :].strip():
            return data
    raise AssertionError(f"没有在输出中找到 JSON：{stdout}")


class TemplateExportProviderTests(unittest.TestCase):
    def run_template(self, *args: str) -> dict:
        env = {
            **os.environ,
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        }
        result = subprocess.run(
            [sys.executable, str(TEMPLATE_SCRIPT), *args],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=True,
        )
        return parse_last_json(result.stdout)

    def test_template_export_scans_and_exports_selected_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            output = root / "output"
            (source / "docs").mkdir(parents=True)
            (source / "docs" / "hello.md").write_text("# Hello\n", encoding="utf-8")
            (source / "skip.md").write_text("# Skip\n", encoding="utf-8")

            scan = self.run_template("--scan-toc", "--source-dir", str(source))
            report = self.run_template(
                "--export",
                "--source-dir",
                str(source),
                "--output",
                str(output),
                "--doc-id",
                "docs/hello.md",
            )

            self.assertEqual(scan["totalDocs"], 2)
            self.assertEqual(scan["folderCount"], 1)
            self.assertEqual(report["provider"], "your-provider")
            self.assertEqual(report["mode"], "export")
            self.assertEqual(report["totalDocs"], 1)
            self.assertEqual(report["exportedDocs"], 1)
            self.assertEqual(report["successCount"], 1)
            self.assertEqual(report["failureCount"], 0)
            self.assertTrue((output / "docs" / "hello.md").exists())
            self.assertFalse((output / "skip.md").exists())


if __name__ == "__main__":
    unittest.main()
