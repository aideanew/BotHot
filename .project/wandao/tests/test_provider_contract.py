import json
import unittest
from pathlib import Path

from scripts import validate_providers


REPO_ROOT = Path(__file__).resolve().parents[1]
PROVIDER_SCHEMA = REPO_ROOT / "providers" / "provider.schema.json"


class ProviderContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(PROVIDER_SCHEMA.read_text(encoding="utf-8"))

    def test_provider_schema_v1_is_present_and_stable(self) -> None:
        self.assertEqual(self.schema["title"], "Wandao Provider Manifest v1")
        self.assertEqual(self.schema["properties"]["schemaVersion"]["const"], 1)
        self.assertTrue(self.schema.get("additionalProperties"))

    def test_schema_enums_match_provider_validator(self) -> None:
        properties = self.schema["properties"]

        self.assertEqual(set(properties["type"]["enum"]), validate_providers.PROVIDER_TYPES)
        self.assertEqual(set(properties["group"]["enum"]), validate_providers.PROVIDER_GROUPS)
        self.assertEqual(set(properties["trustLevel"]["enum"]), validate_providers.TRUST_LEVELS)
        self.assertEqual(set(properties["status"]["enum"]), validate_providers.STATUSES)
        self.assertEqual(set(self.schema["$defs"]["field"]["properties"]["type"]["enum"]), validate_providers.FIELD_TYPES)
        self.assertEqual(set(self.schema["$defs"]["action"]["properties"]["kind"]["enum"]), validate_providers.ACTION_KINDS)

    def test_bundled_provider_manifests_reference_local_schema(self) -> None:
        manifests = sorted((REPO_ROOT / "providers").glob("*/provider.json"))
        self.assertTrue(manifests)
        for manifest in manifests:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(data["schemaVersion"], 1, manifest.as_posix())
            self.assertEqual(data.get("$schema"), "../provider.schema.json", manifest.as_posix())

    def test_provider_docs_declare_v1_compatibility_contract(self) -> None:
        docs = "\n".join(
            [
                (REPO_ROOT / "docs" / "Provider接入说明.md").read_text(encoding="utf-8"),
                (REPO_ROOT / "docs" / "插件开发指南.md").read_text(encoding="utf-8"),
            ]
        )

        self.assertIn("Provider v1", docs)
        self.assertIn("schemaVersion: 1", docs)
        self.assertIn("向后兼容", docs)


if __name__ == "__main__":
    unittest.main()
