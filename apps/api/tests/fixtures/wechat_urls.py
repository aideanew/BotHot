"""微信文章 URL 形态样本（STEP-00 / S0.3.1）。

存在理由：D-01/D-01b 之所以长期无测试覆盖，是因为既有夹具用的形状根本不真实——
`apps/api/tests/test_p0_asset_cache.py:25` 的 `URL_A` 是短链路径却挂 `?biz=`（微信长链
的真实参数名是 `__biz`，见 `app/services/kb.py:587-593` 只读 `biz` 的缺陷），
全库没有一条用**两篇不同长链**做入库的用例（`docs/任务规划V0.2.0/02-数据采集链路穿透
分析.md` §D-01「为何测试没抓到」）。本模块提供 STEP-01 先红用例的唯一样本源。

形状来源（每个常量的锚，逐条可复算）：
- LONG_A / LONG_B       探针 P-3 `docs/任务规划V0.2.0/evidence/probe_longlink_collision.py:14-15`
                         （同 `__biz`、`mid` 2650000001 vs 2650000002）
- LONG_A_TRACKING       `.project/wandao/tests/test_wechat_export.py:23-24`（TRACKED_URL 加
                         `chksm/scene/from` + `#wechat_redirect` 片段）与
                         `docs/任务规划V0.2.0/steps/STEP-01-文章幂等键修复.md:37` 的追踪参数清单
- SHORT_1               `apps/api/tests/test_resolver.py:68` `SHORT_URL`
- MALFORMED_LONG        `apps/api/tests/test_d04_short_link.py:22` 的 `__biz=…&id=1` 形（缺 mid）
- OFFSITE               宿主与 `apps/api/app/providers/article_sources/rss.py:349-354` 登记的
                         阮一峰源一致；非 `ALLOWED_HOSTS`（`app/providers/source_resolver.py:24`）

口径：`__biz` 值取探针的 `MjM5MjgwNTQ1MQ==`（未 URL 编码形态）。编码形态（`%3D%3D`）
在 `apps/api/tests/test_manifest_sync.py:220` 与 `.project/wandao/tests/test_wechat_export.py:23`
均出现过，STEP-01 的 `parse_wechat_url` 必须两者都能解出同一 biz——本模块只给未编码形态，
编码形态由 S1.2.1 用例自行 `quote()` 生成，避免常量表膨胀。
"""

from __future__ import annotations

__all__ = [
    "BIZ_A",
    "FEED_RUANYIFENG",
    "LONG_A",
    "LONG_A_TRACKING",
    "LONG_B",
    "MALFORMED_LONG",
    "OFFSITE",
    "SHORT_1",
    "SHORT_TOKEN_1",
    "SHORT_WITH_FAKE_BIZ_PARAM",
]

#: 公众号 biz（`__biz` 参数值）。同一账号下 LONG_A/LONG_B 只差 `mid` ⇒ D-01 的坍缩
#: 恰好发生在这对上：`kb._article_key` 的**旧口径**令两者同为 `"s"`（S2.2.3 之前）；
#: 规范键上线后两支各自独立，退化形态由 `test_article_identity.py` 与
#: `test_batch_ingest_key_drift.py` 钉住不再回归。
BIZ_A = "MjM5MjgwNTQ1MQ=="

LONG_A = f"https://mp.weixin.qq.com/s?__biz={BIZ_A}&mid=2650000001&idx=1&sn=aaaa1111"
LONG_B = f"https://mp.weixin.qq.com/s?__biz={BIZ_A}&mid=2650000002&idx=1&sn=bbbb2222"

#: 与 LONG_A **同一篇**，只追加追踪参数与片段 ⇒ canonical key 必须与 LONG_A 相等
#: （S1.2.1 ②）。参数集取自 wandao TRACKED_URL 并补齐 STEP-01 清单里的 sessionid/srcid。
LONG_A_TRACKING = (
    f"{LONG_A}&chksm=f2b6330c&scene=27&sessionid=1727337600&srcid=1012"
    "&from=timeline&ascene=1&devicetype=iOS17&version=1800&lang=zh_CN"
    "&pass_ticket=FAKETICKET%3D#wechat_redirect"
)

#: 短链 token：路径即 id，无 query。
SHORT_TOKEN_1 = "AbCdEfGh123"
SHORT_1 = f"https://mp.weixin.qq.com/s/{SHORT_TOKEN_1}"

#: 畸形长链：`/s?` 路径却缺 `mid`（只有 `id`）⇒ canonical key 必须降级到 `h:` 前缀
#: （S1.2.1 ⑤），且 `_article_key` 旧实现同样坍缩为 `"s"`（D-01 的第二类触发形态）。
MALFORMED_LONG = f"https://mp.weixin.qq.com/s?__biz={BIZ_A}&id=1"

#: 非微信域名：`normalize_article_url` 应抛 `MalformedUrlError`（10006），
#: canonical key 走 `h:` 分支（S1.2.1 ④）。D-07（RSS 外链拒收）用同一形态断言。
OFFSITE = "https://www.ruanyifeng.com/blog/2019/09/restful.html"

#: RSS 镜像源自址（发现层用，不入库）；与 `rss.py:349-354` 预置源一致。
FEED_RUANYIFENG = "https://www.ruanyifeng.com/blog/atom.xml"

#: ⚠ 反例，勿用于新用例：短链路径 + 伪 `biz=`/`hid=` 参数（`biz` 不是微信真实参数名）。
#: 保留它是为了 STEP-09 / S9.2.2 有据可改——`test_p0_asset_cache.py:25` 正是用这个形状
#: 把 D-01b「只读 biz 不读 __biz」的缺陷掩盖掉的。
SHORT_WITH_FAKE_BIZ_PARAM = f"https://mp.weixin.qq.com/s/p0-cache-001?biz={BIZ_A}&hid=h0"
