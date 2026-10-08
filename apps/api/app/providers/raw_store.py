"""资产原文存储抽象（BE-02）：raw_uri 存储后端可切换，接口稳定，不强上 S3。

设计（SPEC §四「原文」层）：
- 引擎只收文件/文本上传，原文（content_markdown）由资产层持久化；
- raw_uri 语义：原文可重取地址——默认「URL 透传」（raw_uri = 原文 URL，零回归），
  可选「本地卷」（落盘到可配置目录，返回 file:// URI），S3/OSS 留扩展槽位；
- 后端选择走 config.raw_store_backend（url|local），代码零硬编码。

为什么默认 URL 透传：现有实现 raw_uri = article.url（SPEC §五 F1 现状），
切 local 属行为变更，须由部署方显式开启；P0 缓存命中路径 raw_uri 复用既有值。
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings


class RawStore(Protocol):
    """原文存储端口：save → 返回可重取地址（raw_uri）。"""

    backend: str

    async def save(self, *, url: str, content_markdown: str, title: str) -> str:
        """持久化原文并返回 raw_uri。"""
        ...


class UrlPassthroughStore:
    """默认后端：raw_uri = 原文 URL（现状零回归）。"""

    backend = "url"

    async def save(self, *, url: str, content_markdown: str, title: str) -> str:
        return url


class LocalVolumeStore:
    """本地卷后端：正文落盘到 raw_store_dir，返回 file:// URI。

    文件命名：sha256(原文URL + 正文hash) 前缀 + .md——同文多次 save 幂等覆盖（原子写）。
    S3/OSS 扩展：新类实现 RawStore 协议，config.raw_store_backend 切换，调用方零改动。
    """

    backend = "local"

    def __init__(self, base_dir: str | Path | None = None) -> None:
        settings = get_settings()
        raw_dir = Path(base_dir) if base_dir else Path(str(settings.raw_store_dir or ""))
        if not str(raw_dir):
            # 兜底：backend 数据目录下 raw/（不写工作区外敏感路径）
            raw_dir = Path(__file__).resolve().parents[2] / "data" / "raw"
        self._dir = raw_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    async def save(self, *, url: str, content_markdown: str, title: str) -> str:
        digest = hashlib.sha256(f"{url}|{content_markdown}".encode()).hexdigest()[:24]
        safe = _slug(title)[:40] or "article"
        target = self._dir / f"{safe}-{digest}.md"
        tmp = target.with_suffix(".md.tmp")
        tmp.write_text(content_markdown, encoding="utf-8")
        tmp.replace(target)
        return target.as_uri()


def _slug(text: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\s]+", "_", (text or "").strip())
    return cleaned or "article"


def make_raw_store(backend: str | None = None) -> RawStore:
    """按 config.raw_store_backend 装配（url 默认 / local 本地卷；未知回落 url）。"""
    settings = get_settings()
    chosen = backend or settings.raw_store_backend
    if chosen == "local":
        return LocalVolumeStore()
    return UrlPassthroughStore()
