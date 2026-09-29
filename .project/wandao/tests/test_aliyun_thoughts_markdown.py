import unittest
import tempfile
from pathlib import Path

from export_aliyun_thoughts import Node, build_paths, ensure_document_parent_dirs, slate_value_to_markdown


def text_node(text: str) -> dict:
    return {"object": "text", "leaves": [{"text": text}]}


def code_line(text: str) -> dict:
    return {"object": "block", "type": "code-line", "nodes": [text_node(text)]}


class AliyunThoughtsMarkdownTests(unittest.TestCase):
    def test_code_block_preserves_slate_line_boundaries(self) -> None:
        value = {
            "document": {
                "nodes": [
                    {
                        "object": "block",
                        "type": "code-block",
                        "data": {"language": "java"},
                        "nodes": [
                            code_line("public class Demo {"),
                            code_line("    return;"),
                            code_line("}"),
                        ],
                    }
                ]
            }
        }

        markdown = slate_value_to_markdown(value, "demo")["markdown"]

        self.assertIn("```java\npublic class Demo {\n    return;\n}\n```", markdown)
        self.assertNotIn("public class Demo {    return;}", markdown)

    def test_code_block_preserves_blank_lines_inside_fence(self) -> None:
        value = {
            "document": {
                "nodes": [
                    {
                        "object": "block",
                        "type": "code-block",
                        "data": {"language": "text"},
                        "nodes": [
                            code_line("第一行"),
                            code_line(""),
                            code_line("第三行"),
                        ],
                    }
                ]
            }
        }

        markdown = slate_value_to_markdown(value, "demo")["markdown"]

        self.assertIn("```text\n第一行\n\n第三行\n```", markdown)

    def test_selected_export_only_creates_selected_parent_folders(self) -> None:
        nodes = [
            Node("folder-1", "01-应该导出", "folder", None, 1, {}),
            Node("doc-1", "文档 A", "document", "folder-1", 1, {}),
            Node("folder-2", "02-不应该导出", "folder", None, 2, {}),
            Node("doc-2", "文档 B", "document", "folder-2", 1, {}),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            _folder_paths, planned_doc_paths, _children, _root_items = build_paths(nodes, output)

            ensure_document_parent_dirs([nodes[1]], planned_doc_paths, output)

            self.assertTrue((output / "01-01-应该导出").exists())
            self.assertFalse((output / "02-02-不应该导出").exists())


if __name__ == "__main__":
    unittest.main()
