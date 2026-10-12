"""微信文章 URL 的身份解析（STEP-02 / S2.1.2，P0-1 前半）。

职责边界：只做**形态解析**——把一条 URL 拆成「号主 + 文章」的组成部分，供
`kb`（S2.1.3 起委托本模块）与规范键（S2.2，待 ADR-0011）使用。纯函数、零 IO、
不查库、不抓取、不抛业务异常：无法识别的输入一律以空串字段返回，由调用方决定降级路径。

为什么单独成模块（而不是继续在 `app/services/kb.py` 里打补丁）：
改前的 `kb._biz_from_url` 只读 `biz`，而微信长链的真实参数名是 `__biz`
（形状见 `apps/api/tests/fixtures/wechat_urls.py:45`），长链入库时 biz 恒为空串；
`kb.py:554-557` 的 `_article_key` 取 URL 末段，长链末段是 `s` ⇒ 同账号两篇文章坍缩为同一键
（探针 P-3，`docs/任务规划V0.2.0/evidence/probe_longlink_collision.py`）。
身份口径必须只有一处定义，否则「解析」与「幂等键」会在两个文件里各说各话
——S2.1.3 已把 `kb._biz_from_url` 改成委托本模块（`kb.py:587-591`），这段是**改前根因**的记录。
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

__all__ = ["WECHAT_HOST", "WechatUrlParts", "parse_wechat_url"]

WECHAT_HOST = "mp.weixin.qq.com"

_SHORT_PATH_PREFIX = "/s/"
#: 微信长链省略 `idx` 时语义即「该条推送的第 1 篇」（卡面 S2.1.2）。
_DEFAULT_IDX = "1"


@dataclass(frozen=True)
class WechatUrlParts:
    """一条 URL 的身份组成部分，字段口径三句话：

    - `host` 是原样（小写折叠后的）netloc，含端口与 userinfo，不做白名单；
    - **查询参数不因 host 不是微信而停止解析**——非微信域名带 `__biz`/`mid` 也会被解出。
      这是当前口径而非漏洞修复：`kb._biz_from_url` 的既有行为同样与 host 无关（S2.1.3 委托后
      若加 host 闸门会改变所有非微信源的 biz 解析结果，超出本卡范围），已登记为 S2.2 待定项；
    - `idx` 是唯一恒非空的字段：微信省略 `idx` 即「该条推送第 1 篇」，按卡面补 `'1'`。
    """

    biz: str = ""
    mid: str = ""
    idx: str = ""
    sn: str = ""
    short_token: str = ""
    host: str = ""


def _first(query: dict[str, list[str]], name: str) -> str:
    values = query.get(name)
    return values[0] if values else ""


def parse_wechat_url(url: str) -> WechatUrlParts:
    """URL → `WechatUrlParts`；`__biz` 优先于 `biz`，`idx` 缺省 `'1'`，短链取路径末段为 token。

    两条解码口径（都会影响身份键，故写在这里而不是留给调用方猜）：

    1. 百分号解码由 `parse_qs` 完成 ⇒ `%3D%3D` 与 `==` 两种 `__biz` 书写结果相同。
    2. **`+` 按字面加号处理**：先把查询串里的 `+` 改写成 `%2B` 再解析。`parse_qs` 默认走
       `application/x-www-form-urlencoded` 口径（`+` = 空格），而 `__biz` 是 base64、字符集含 `+`，
       于是同一个号主的 biz 会因「链接里写的是 `+` 还是 `%2B`」解出两个不同值 ⇒ 一篇文章裂成两条
       资产（数据黑洞形态）。改写后 `a+b` 与 `a%2Bb` 都解为 `a+b`；代价是查询串里以 `+` 表示的
       空格不再还原为空格，而本模块读的五个参数（`__biz/biz/mid/idx/sn`）没有取空格值的形态。
    3. 非 `str` 入参（含 `None`、`bytes`）返回全空字段而不抛：调用方传的是 `Source.url` 这类
       可为 NULL 的库字段，解析层不应把数据质量问题变成抓取链路的异常。
    """
    if not isinstance(url, str):
        return WechatUrlParts()
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    query = parse_qs(parsed.query.replace("+", "%2B"))
    short_token = ""
    if host == WECHAT_HOST and parsed.path.startswith(_SHORT_PATH_PREFIX):
        short_token = parsed.path[len(_SHORT_PATH_PREFIX) :].strip("/")
    return WechatUrlParts(
        biz=_first(query, "__biz") or _first(query, "biz"),
        mid=_first(query, "mid"),
        idx=_first(query, "idx") or _DEFAULT_IDX,
        sn=_first(query, "sn"),
        short_token=short_token,
        host=host,
    )
