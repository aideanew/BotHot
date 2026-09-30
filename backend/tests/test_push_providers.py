"""BotHot 推送 Provider 单元测试。

验证：
- Provider 注册表完整性
- 飞书/钉钉/企业微信签名计算正确性
- 未配置 webhook_url 时的诚实回执
- 各渠道消息格式正确性
"""

import base64
import hashlib
import hmac
from datetime import UTC
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.providers.push import (
    PUSH_CHANNELS,
    PushMessage,
    make_push_provider,
    registered_channels,
)
from app.providers.push.dingtalk import DingtalkPushProvider
from app.providers.push.dingtalk import _sign as dingtalk_sign
from app.providers.push.feishu import FeishuPushProvider
from app.providers.push.feishu import _sign as feishu_sign
from app.providers.push.web import WebPushProvider
from app.providers.push.webhook import WebhookPushProvider
from app.providers.push.wechat_clawbot import WechatClawbotPushProvider
from app.providers.push.wechat_work import WechatWorkPushProvider


class TestProviderRegistry:
    """Provider 注册表测试。"""

    def test_all_channels_registered(self):
        """六个渠道全部注册。"""
        assert set(PUSH_CHANNELS) == {
            "feishu", "dingtalk", "wechat_work",
            "webhook", "wechat_clawbot", "web",
        }

    def test_registered_channels_returns_metadata(self):
        """registered_channels 返回 channel + implemented + description。"""
        channels = registered_channels()
        assert len(channels) == 6
        for ch in channels:
            assert "channel" in ch
            assert ch["implemented"] is True
            assert isinstance(ch["description"], str) and len(ch["description"]) > 0

    def test_make_push_provider_returns_correct_type(self):
        """make_push_provider 返回正确的 Provider 类型。"""
        assert isinstance(make_push_provider("feishu"), FeishuPushProvider)
        assert isinstance(make_push_provider("dingtalk"), DingtalkPushProvider)
        assert isinstance(make_push_provider("wechat_work"), WechatWorkPushProvider)
        assert isinstance(make_push_provider("webhook"), WebhookPushProvider)
        assert isinstance(make_push_provider("wechat_clawbot"), WechatClawbotPushProvider)
        assert isinstance(make_push_provider("web"), WebPushProvider)

    def test_make_push_provider_unknown_raises(self):
        """未知渠道抛 ValueError。"""
        with pytest.raises(ValueError, match="未知推送通道"):
            make_push_provider("telegram")


class TestFeishuProvider:
    """飞书推送 Provider 测试。"""

    def test_sign_correctness(self):
        """飞书加签算法：HMAC-SHA256(timestamp + "\\n" + secret)。"""
        secret = "test_secret_123"
        timestamp = 1700000000
        expected = base64.b64encode(
            hmac.new(f"{timestamp}\n{secret}".encode(), digestmod=hashlib.sha256).digest()
        ).decode("utf-8")
        assert feishu_sign(secret, timestamp) == expected

    @pytest.mark.asyncio
    async def test_no_webhook_returns_honest_failure(self):
        """未配置 webhook_url 时返回诚实失败（不伪造成功）。"""
        provider = FeishuPushProvider()
        msg = PushMessage(message="test")
        result = await provider.push(msg)
        assert result.delivered is False
        assert "webhook_url 未配置" in result.reason
        assert result.channel == "feishu"

    @pytest.mark.asyncio
    async def test_successful_push(self):
        """模拟飞书成功响应。"""
        provider = FeishuPushProvider()
        msg = PushMessage(
            webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/test",
            message="测试消息",
            title="测试标题",
        )
        mock_response = MagicMock()
        mock_response.json.return_value = {"StatusCode": 0, "StatusMessage": "success"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_instance

            result = await provider.push(msg)
            assert result.delivered is True
            assert result.channel == "feishu"


class TestDingtalkProvider:
    """钉钉推送 Provider 测试。"""

    def test_sign_correctness(self):
        """钉钉加签算法：HMAC-SHA256(secret, timestamp + "\\n" + secret)。"""
        import urllib.parse
        secret = "test_secret_456"
        timestamp = 1700000000000
        string_to_sign = f"{timestamp}\n{secret}"
        hmac_code = hmac.new(
            secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        expected = urllib.parse.quote_plus(base64.b64encode(hmac_code).decode("utf-8"))
        actual_ts, actual_sign = dingtalk_sign(secret, timestamp)
        assert actual_ts == str(timestamp)
        assert actual_sign == expected

    @pytest.mark.asyncio
    async def test_no_webhook_returns_honest_failure(self):
        """未配置 webhook_url 时返回诚实失败。"""
        provider = DingtalkPushProvider()
        msg = PushMessage(message="test")
        result = await provider.push(msg)
        assert result.delivered is False
        assert "webhook_url 未配置" in result.reason

    @pytest.mark.asyncio
    async def test_successful_push(self):
        """模拟钉钉成功响应。"""
        provider = DingtalkPushProvider()
        msg = PushMessage(
            webhook_url="https://oapi.dingtalk.com/robot/send?access_token=test",
            message="测试消息",
        )
        mock_response = MagicMock()
        mock_response.json.return_value = {"errcode": 0, "errmsg": "ok"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_instance

            result = await provider.push(msg)
            assert result.delivered is True


class TestWechatWorkProvider:
    """企业微信推送 Provider 测试。"""

    @pytest.mark.asyncio
    async def test_no_webhook_returns_honest_failure(self):
        """未配置 webhook_url 时返回诚实失败。"""
        provider = WechatWorkPushProvider()
        result = await provider.push(PushMessage(message="test"))
        assert result.delivered is False
        assert "webhook_url 未配置" in result.reason


class TestWebhookProvider:
    """通用 Webhook 推送 Provider 测试。"""

    @pytest.mark.asyncio
    async def test_no_webhook_returns_honest_failure(self):
        provider = WebhookPushProvider()
        result = await provider.push(PushMessage(message="test"))
        assert result.delivered is False
        assert "webhook_url 未配置" in result.reason


class TestWechatClawbotProvider:
    """微信 ClawBot 推送 Provider 测试。"""

    @pytest.mark.asyncio
    async def test_no_base_url_returns_honest_failure(self):
        provider = WechatClawbotPushProvider()
        result = await provider.push(PushMessage(message="test"))
        assert result.delivered is False
        assert "base_url 未配置" in result.reason

    @pytest.mark.asyncio
    async def test_no_user_id_returns_honest_failure(self):
        provider = WechatClawbotPushProvider()
        result = await provider.push(PushMessage(message="test", webhook_url="http://clawbot:8080"))
        assert result.delivered is False
        assert "external_user_id 未配置" in result.reason


class TestPushScheduler:
    """推送调度器测试。

    W1 起 cron 解析统一收口到 app.services.cron_expr（croniter 后端，简写格式
    兼容翻译为标准 5 段）；调度器自身不再暴露 _parse_cron_next，测试直接测解析模块。
    """

    def test_parse_cron_hh_mm(self):
        """HH:MM 格式解析。"""
        from datetime import datetime

        from app.services.cron_expr import parse_cron_next as _parse_cron_next

        now = datetime(2026, 9, 29, 8, 0, 0, tzinfo=UTC)
        next_run = _parse_cron_next("10:00", now)
        assert next_run is not None
        assert next_run.hour == 10
        assert next_run.minute == 0

    def test_parse_cron_every_n_hours(self):
        """*/N 小时格式解析（croniter 语义：对齐到下一个小整点，非 now+N 小时）。"""
        from datetime import datetime

        from app.services.cron_expr import parse_cron_next as _parse_cron_next

        now = datetime(2026, 9, 29, 8, 0, 0, tzinfo=UTC)
        next_run = _parse_cron_next("*/3", now)
        assert next_run is not None
        assert next_run.hour == 9  # "0 */3 * * *" 下个触发点 09:00（对齐整点）

    def test_parse_cron_every_n_minutes(self):
        """纯数字 N 分钟格式解析。"""
        from datetime import datetime

        from app.services.cron_expr import parse_cron_next as _parse_cron_next

        now = datetime(2026, 9, 29, 8, 0, 0, tzinfo=UTC)
        next_run = _parse_cron_next("30", now)
        assert next_run is not None
        assert next_run.minute == 30

    def test_parse_cron_invalid_returns_none(self):
        """无效 cron 返回 None。"""
        from datetime import datetime

        from app.services.cron_expr import parse_cron_next as _parse_cron_next

        now = datetime(2026, 9, 29, 8, 0, 0, tzinfo=UTC)
        assert _parse_cron_next("", now) is None
        assert _parse_cron_next("invalid", now) is None

    def test_parse_cron_past_time_advances_to_next_day(self):
        """过去的时间点推进到次日。"""
        from datetime import datetime

        from app.services.cron_expr import parse_cron_next as _parse_cron_next

        now = datetime(2026, 9, 29, 15, 0, 0, tzinfo=UTC)
        next_run = _parse_cron_next("10:00", now)
        assert next_run is not None
        assert next_run.day == 30  # 次日
        assert next_run.hour == 10

    def test_parse_cron_standard_5_field(self):
        """标准 5 段式直通（W1 新增能力）。"""
        from datetime import datetime

        from app.services.cron_expr import parse_cron_next as _parse_cron_next

        now = datetime(2026, 9, 29, 8, 0, 0, tzinfo=UTC)
        next_run = _parse_cron_next("30 9 * * 1-5", now)
        assert next_run is not None
        assert next_run.hour == 9
        assert next_run.minute == 30
