"""探针 P-1：四家付费源的行形状经 manifest._map_row 后是否可用；RSS pubDate 是否可解析。
2026-10-12 @61739f0 实测：dajiala/justoneapi -> None（整行被 skip），rss publish_time=None，atom 正常。
用法：cd apps/api && .venv/bin/python evidence/probe_row_mapping.py
"""
from app.services.manifest import _map_row
from app.providers.article_sources.rss import _parse_feed
rows = {
 "dajiala": {"url":"https://mp.weixin.qq.com/s/abc","title":"t","digest":"d","publish_time":"1790659200"},
 "justoneapi": {"url":"https://mp.weixin.qq.com/s?__biz=X&mid=1&idx=1&sn=a","title":"t","digest":"d","publish_time":"1790659200"},
 "redfox": {"workUuid":"a"*32,"workUrl":"https://mp.weixin.qq.com/s/x","title":"t","publishTime":"2026-09-27 07:42:00"},
}
for k,r in rows.items(): print(k, "->", _map_row(r))
rss='''<?xml version="1.0"?><rss version="2.0"><channel><title>x</title><item><title>A</title><link>https://ex.com/a</link><guid>https://ex.com/a</guid><pubDate>Mon, 12 Oct 2026 07:00:00 +0000</pubDate></item></channel></rss>'''
items=_parse_feed(rss); print("rss item", items[0]); print("rss ->", _map_row(items[0]))
atom='''<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry><title>B</title><link href="https://ex.com/b"/><id>tag:b</id><updated>2026-10-12T07:00:00Z</updated></entry></feed>'''
it=_parse_feed(atom); print("atom ->", _map_row(it[0]))
