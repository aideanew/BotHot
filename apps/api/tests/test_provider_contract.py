"""STEP-03 / S3.1.1：全渠道清单行契约的参数化门（P-1 的常驻版）。

一句话判据：**每家 provider 的样本清单行，经 `manifest._map_row` 都必须得到非 None**，
且行内 `id` / `url` / `title` 三个键齐备。

改前的红（P-1 读数）：dajiala / justoneapi / tikhub / wellbyte 四家**整页被静默丢掉**——
它们的行里没有任何 id 类键（改前只有 `url`/`title`/`digest`/`publish_time`，本批把时间键统一成
`publishTime` 并补上 `id`），而 `_map_row` 在缺 id 时 `return None`（`app/services/manifest.py`
的 `_ID_KEYS` 那一支），`sync_source` 对 None 行
`return None`（`app/services/manifest.py` 的 `_ID_KEYS` 那一支），`sync_source` 对 None 行
直接 `continue` 且不记 `skipped` 之外的账 ⇒ 上游返回 4 条、本地落 0 条，而日志看着像成功。
redfox 绿（上游给 `workUuid`）、rss 绿（自己合成 id）。

为什么门开在"样本 × 行"而不是"provider 单测"：
1. 参数化 id 用**样本文件名** ⇒ 新样本自动纳入，不需要改测试（卡面 S3.1.1.2）；
2. 本文件还有一条"样本必须被认领"的守卫（`test_every_sample_is_claimed_by_a_case`）——
   自动纳入这件事本身要有人守，否则加进去的样本目录与用例表会分叉，
   而分叉的方向恰好是"新渠道静默不测"，那正是这张卡要消灭的形状。

样本是**合成占位值**（见 `tests/fixtures/provider_payloads/README.md`），
所以本文件判的是"形状与链路"，不判"上游真实字段"——活体核实归 STEP-08 S8.5.1，
卡面 R-1 明写本步以样本为准。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.core.errors import DependencyUnavailableError
from app.providers.article_sources.dajiala import DajialaClient
from app.providers.article_sources.justoneapi import JustOneApiClient
from app.providers.article_sources.tikhub import TikhubClient
from app.providers.article_sources.wellbyte import WellbyteClient
from app.providers.redfox.client import RedfoxClient
from app.services.manifest import _ID_KEYS, _TITLE_KEYS, _URL_KEYS, _first_str, _map_row

SAMPLE_DIR = Path(__file__).parent / "fixtures" / "provider_payloads"

# 样本名 → (构造器, identifier)。构造器收到一个已注入 MockTransport 的 http 客户端。
_BUILDERS: dict[str, Callable[[httpx.AsyncClient], Any]] = {
    "dajiala": lambda http: DajialaClient(api_key="test-key", http=http),
    "justoneapi": lambda http: JustOneApiClient(api_key="test-key", http=http),
    "tikhub": lambda http: TikhubClient(api_key="test-key", http=http),
    "wellbyte": lambda http: WellbyteClient(api_key="test-key", http=http),
    "redfox": lambda http: RedfoxClient(base_url="https://redfox.test", api_key="test-key", http=http),
}
# identifier 只是占位入参（清单键的形状与它无关）；RSS 走 test_rss_provider.py，不在这里。
_IDENTIFIER = "MjM5MjgwNTQ1MQ=="

# S3.2.1–4 的改造范围：这四家必须输出字面 `id`（`WorkListRow.id`）。
# redfox 不在其中——它是上游原样透传的参照实现，键名归一不归本卡。
_CANONICAL_ID = ("dajiala", "justoneapi", "tikhub", "wellbyte")


def _client(sample: str) -> httpx.AsyncClient:
    """把样本原样回成上游响应：任何 URL 都返回它，provider 自己的解析路径照常走。"""
    path = SAMPLE_DIR / f"{sample}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return httpx.AsyncClient(transport=httpx.MockTransport(_handler))


async def _rows(sample: str) -> list[dict[str, Any]]:
    provider = _BUILDERS[sample](_client(sample))
    try:
        rows, _total = await provider.query_work_list(_IDENTIFIER, 1)
    finally:
        await provider.aclose()
    return rows


@pytest.mark.parametrize("sample", sorted(_BUILDERS))
async def test_sample_yields_rows(sample: str) -> None:
    """前提守卫：样本必须真的产出行。空列表会让下面两条断言**空转成真**。"""
    rows = await _rows(sample)
    assert rows, f"{sample} 的样本经 provider 解析后一行都没有——链路或样本变了，下面两条会失去判定力"


@pytest.mark.parametrize("sample", sorted(_BUILDERS))
async def test_rows_carry_id_url_title(sample: str) -> None:
    """契约面（第一层，全渠道）：每行都必须能解出 id/url/title —— 按**别名组**判，不按字面键名判。

    为什么不写死 `row["id"]`：redfox 是上游原样透传（`workUuid`/`workUrl`/`publishTime`，
    `client.py` 的 `query_work_list` 零归一），而卡面 S3.2 的改造范围是四家付费 provider，
    改 redfox 的输出键名不在本卡授权内（它会连带动 `test_manifest_sync` 的一串上游形状断言）。
    别名组就是 `_map_row` 自己用的那一组 ⇒ 这一层判的是"消费端能不能解出来"，与 P-1 同源。

    第二层（`test_canonical_id_key_on_normalized_channels`）才判字面 `id`：
    那是 S3.2.1–4 的产出物，缺了就说明"归一"没真发生。
    """
    for i, row in enumerate(await _rows(sample)):
        assert _first_str(row, _ID_KEYS), f"{sample} 第 {i} 行解不出 id：{_keys(row)}"
        assert _first_str(row, _URL_KEYS), f"{sample} 第 {i} 行解不出 url：{_keys(row)}"
        assert _first_str(row, _TITLE_KEYS), f"{sample} 第 {i} 行解不出 title：{_keys(row)}"


@pytest.mark.parametrize("sample", sorted(_CANONICAL_ID))
async def test_canonical_id_key_on_normalized_channels(sample: str) -> None:
    """契约面（第二层，S3.2 改造范围内的渠道）：行里必须**真的**有 `id` 键。

    只在别名组上判会放过一种情况：provider 依旧只写 `workUuid`，测试照样绿，
    而卡面"所有 provider 输出 `WorkListRow`"从未成立——所以这一层单独钉。
    """
    for i, row in enumerate(await _rows(sample)):
        assert str(row.get("id") or ""), f"{sample} 第 {i} 行没有规范键字段 `id`：{_keys(row)}"


@pytest.mark.parametrize("sample", sorted(_BUILDERS))
async def test_rows_survive_map_row(sample: str) -> None:
    """消费面：`_map_row` 不许再把任何一行判成 None（整页静默丢弃的那条路径）。

    这条与上面两条**不是重复**：上面判 provider 产出，这条判 manifest 消费；
    任一端回退都会红，两端同时退化也照样红。
    """
    for i, row in enumerate(await _rows(sample)):
        mapped = _map_row(row)
        assert mapped is not None, f"{sample} 第 {i} 行被 `_map_row` 判成不可用（P-1 形状）：{_keys(row)}"
        assert mapped["external_id"] == _first_str(row, _ID_KEYS), (
            f"{sample} 第 {i} 行的 id 没被当 external_id 用：{mapped['external_id']!r}"
        )


def _keys(row: dict[str, Any]) -> list[str]:
    return sorted(row)


@pytest.mark.parametrize("sample", sorted(_BUILDERS))
async def test_missing_key_fails_loudly_instead_of_empty_list(sample: str) -> None:
    """没有 Key 必须**显式失败**，不许返回空清单冒充成功（仓库既有口径，redfox 那条注释写得很清楚）。

    这条与上面三条判的是同一族缺陷的另一半：`_map_row` 丢整行是"静默"，
    `query_work_list` 返回 `[]` 也是"静默"——两者都会让一轮同步看起来正常而实际零入库。
    """
    provider = _BUILDERS[sample](_client(sample))
    provider._api_key = ""  # noqa: SLF001  四家与 redfox 都用同一个 `self._api_key` 名字
    try:
        with pytest.raises(DependencyUnavailableError):
            await provider.query_work_list(_IDENTIFIER, 1)
    finally:
        await provider.aclose()


def test_every_sample_is_claimed_by_a_case() -> None:
    """样本目录里的每个 payload 都必须被某个用例认领——"自动纳入"这件事本身要有门。

    没有这条，新增一家渠道的样本会静静躺在目录里、谁都看不见，
    而上面三条的绿灯会被读成"全渠道已覆盖"。
    """
    files = {p.stem for p in SAMPLE_DIR.glob("*.json")} | {p.stem for p in SAMPLE_DIR.glob("*.xml")}
    rss_only = {"rss2", "atom"}  # RSS 的解析面由 tests/test_rss_provider.py 判（S3.1.2）
    unclaimed = sorted(files - set(_BUILDERS) - rss_only)
    assert not unclaimed, f"样本未被任何用例认领：{unclaimed}——请加进 _BUILDERS 或显式登记到 RSS/其它归属"
    # 第二层的名单必须是第一层的子集：写错一个名字，那家渠道就从"判字面 id"里静默消失。
    stray = sorted(set(_CANONICAL_ID) - set(_BUILDERS))
    assert not stray, f"_CANONICAL_ID 里有不在 _BUILDERS 的名字（参数化会空转）：{stray}"
