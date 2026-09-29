import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_SCRIPT = REPO_ROOT / "providers" / "_template_import" / "actions.py"


def parse_last_json(stdout: str) -> dict:
    decoder = json.JSONDecoder()
    for index, char in enumerate(stdout):
        if char != "{":
            continue
        try:
            data, _end = decoder.raw_decode(stdout[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and not stdout[index + _end :].strip():
            return data
    raise AssertionError(f"没有在输出中找到 JSON：{stdout}")


class TemplateImportProviderTests(unittest.TestCase):
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

    def test_template_import_scans_and_copies_markdown_resources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            output = root / "output"
            assets = source / "docs" / "assets"
            assets.mkdir(parents=True)
            (assets / "pic.png").write_bytes(b"fake image")
            (source / "docs" / "hello.md").write_text(
                "# Hello\n\n![pic](assets/pic.png)\n",
                encoding="utf-8",
            )

            scan = self.run_template("--scan-source", "--source-dir", str(source))
            report = self.run_template(
                "--import",
                "--source-dir",
                str(source),
                "--output",
                str(output),
                "--copy-resources",
            )

            self.assertEqual(scan["totalDocs"], 1)
            self.assertEqual(scan["folderCount"], 1)
            self.assertEqual(report["provider"], "your-import-provider")
            self.assertEqual(report["mode"], "import")
            self.assertEqual(report["totalDocs"], 1)
            self.assertEqual(report["importedDocs"], 1)
            self.assertEqual(report["successCount"], 1)
            self.assertEqual(report["failureCount"], 0)
            self.assertEqual(report["attachmentSuccess"], 1)
            self.assertTrue((output / "docs" / "hello.md").exists())
            self.assertTrue((output / "docs" / "assets" / "pic.png").exists())
            self.assertTrue((output / "00-导入报告.json").exists())


if __name__ == "__main__":
    unittest.main()
