"""文本规范化（B-T7，纯函数）：NFC + 选择性全角→半角 + 零宽剔除 + 空白收敛 + 实体兜底。

规则口径（逐条由单测锁定）：
- Unicode NFC 归一（组合字符合并，不激进 NFKC——避免 ㎡/① 等语义改变）；
- 全角→半角：仅数字/字母/常用标点区 U+FF01–U+FF5E（平移 0xFEE0）与全角空格 U+3000；
- 零宽字符剔除：U+200B/200C/200D/2060/U+FEFF；
- 连续空白收敛：段内连续空白 → 单空格；
- HTML 实体兜底解码：html.unescape（convert_charrefs 之后的二次转义兜底）。
"""

from __future__ import annotations

import html as html_lib
import re
import unicodedata
from dataclasses import replace

from app.services.extractor import ExtractedContent, build_langbot_format

_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\u2060\ufeff]")
_WS_RUN_RE = re.compile(r"[ \t\u00a0]{2,}")


def normalize_text(text: str) -> str:
    """单条文本规范化（按模块口径依序应用）。"""
    if not text:
        return text
    # 1) NFC 归一
    out = unicodedata.normalize("NFC", text)
    # 2) 全角→半角：U+FF01–U+FF5E 平移 0xFEE0；全角空格 U+3000 → 半角空格
    out = "".join(
        chr(ord(ch) - 0xFEE0) if 0xFF01 <= ord(ch) <= 0xFF5E else ("\u0020" if ch == "\u3000" else ch)
        for ch in out
    )
    # 3) 零宽字符剔除
    out = _ZERO_WIDTH_RE.sub("", out)
    # 4) HTML 实体兜底解码：循环至稳定（处理 &amp;amp; 等多层二次转义残片，上限防恶意输入）
    if "&" in out:
        for _ in range(3):
            decoded = html_lib.unescape(out)
            if decoded == out:
                break
            out = decoded
    # 5) 连续空白收敛
    out = _WS_RUN_RE.sub(" ", out)
    return out.strip()


def normalize_extracted(extracted: ExtractedContent) -> ExtractedContent:
    """对清洗产物的全部文本字段规范化，并重算 wordCount / 重建 langbotFormat。

    段内空白收敛可能改变字数，故 wordCount 在归一后重算（count_words 同口径）。
    """
    from app.services.extractor import count_words

    paragraphs = [normalize_text(p) for p in extracted.paragraphs]
    paragraphs = [p for p in paragraphs if p]  # 归一后可能产生空段（如原段全是零宽字符）
    images = [replace(img, caption=normalize_text(img.caption) if img.caption else "") for img in extracted.images]
    normalized = replace(
        extracted,
        title=normalize_text(extracted.title),
        author=normalize_text(extracted.author),
        paragraphs=paragraphs,
        images=images,
        word_count=count_words("\n".join(paragraphs)),
    )
    return replace(
        normalized,
        langbot_format=build_langbot_format(
            normalized.title, normalized.author, normalized.publish_time,
            normalized.url, normalized.paragraphs, normalized.images,
        ),
    )
