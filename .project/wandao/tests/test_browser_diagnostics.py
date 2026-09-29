import unittest

from export_aliyun_thoughts import debug_port_error_message


class BrowserDiagnosticsTests(unittest.TestCase):
    def test_debug_port_error_message_mentions_browser_setting_and_port(self) -> None:
        message = debug_port_error_message(9222, "occupied", "端口有响应")

        self.assertIn("9222", message)
        self.assertIn("设置 > 自动化浏览器", message)
        self.assertIn("端口被其他程序占用", message)


if __name__ == "__main__":
    unittest.main()
