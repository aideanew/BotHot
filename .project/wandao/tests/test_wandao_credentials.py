import json
import tempfile
import unittest
from pathlib import Path

from wandao_credentials import write_private_json


class WandaoCredentialsTests(unittest.TestCase):
    def test_private_json_is_atomically_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "credentials.json"

            write_private_json(target, {"token": "first"})
            write_private_json(target, {"token": "second", "cookies": [1, 2]})

            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"token": "second", "cookies": [1, 2]})
            self.assertEqual(list(target.parent.glob(f".{target.name}.*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
