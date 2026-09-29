"""质量评分（B-T7）：ExtractedContent → {score, passed, reasons}。

评分构成（0-100，A 可调常量集中于此）：
- 长度分（60）：wordCount 主导，每 5 字 1 分、300 字封顶；
- 元信息分（20）：标题 10 + 发布时间 5 + 作者 5；
- 结构基准分（20）：有正文即得；
- 惩罚项：纯图无文本 -20；图片字数失衡（wordCount/图片数 < 30）-10；
  重复段落每组 -5（上限 -15）。
passed 阈值 = QUALITY_PASS_THRESHOLD（30）；未达阈值由调用方转 20003。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.extractor import ExtractedContent

# ---- A 调参常量 ----
QUALITY_PASS_THRESHOLD = 30  # 及格线；passed=False → 20003 EXTRACT_QUALITY_LOW
LENGTH_FULL_WORDS = 300  # wordCount 达到即拿满长度分
LENGTH_MAX_SCORE = 60
LENGTH_DIVISOR = 5  # 每 5 字 1 分
META_SCORE = 20  # 标题 10 + 发布时间 5 + 作者 5
STRUCTURE_BASE_SCORE = 20
PENALTY_TEXTLESS = 20  # 纯图无文本
PENALTY_IMG_IMBALANCE = 10  # 图片字数失衡
IMBALANCE_MIN_WORDS_PER_IMAGE = 30  # 每张图至少应摊到 30 字正文
PENALTY_DUPLICATE_PER_GROUP = 5  # 每组重复段落
PENALTY_DUPLICATE_CAP = 15


@dataclass(slots=True)
class QualityVerdict:
    """评分结论（camelCase 视图经 to_view 输出，v0.3f 备案中）。"""

    score: int
    passed: bool
    reasons: list[str] = field(default_factory=list)

    def to_view(self) -> dict:
        return {"qualityScore": self.score, "qualityPassed": self.passed, "qualityReasons": self.reasons}


def _duplicate_groups(paragraphs: list[str]) -> int:
    """完全相同文本出现 ≥2 次的段落户数。"""
    seen: dict[str, int] = {}
    for p in paragraphs:
        seen[p] = seen.get(p, 0) + 1
    return sum(1 for count in seen.values() if count >= 2)


def score_quality(extracted: ExtractedContent) -> QualityVerdict:
    """按模块口径评分；reasons 记录全部扣分/风险项（可观测可调参）。"""
    reasons: list[str] = []

    length_score = min(LENGTH_MAX_SCORE, extracted.word_count // LENGTH_DIVISOR)
    if extracted.word_count < LENGTH_DIVISOR * 10:  # <100 字提示（不扣，仅长度分体现）
        reasons.append(f"正文字数偏少(wordCount={extracted.word_count})")

    meta_score = 0
    if extracted.title:
        meta_score += 10
    else:
        reasons.append("缺少标题")
    if extracted.publish_time:
        meta_score += 5
    else:
        reasons.append("缺少发布时间")
    if extracted.author:
        meta_score += 5
    else:
        reasons.append("缺少作者")

    penalty = 0
    # 结构基准分：有正文段落才给（纯图/空文不拿结构分）
    structure_score = STRUCTURE_BASE_SCORE if extracted.paragraphs else 0
    if not extracted.paragraphs:
        reasons.append("无正文段落")
        if extracted.images:
            penalty += PENALTY_TEXTLESS
            reasons.append("纯图片无正文文本")
    if extracted.paragraphs and extracted.images:
        words_per_image = extracted.word_count / max(1, len(extracted.images))
        if words_per_image < IMBALANCE_MIN_WORDS_PER_IMAGE:
            penalty += PENALTY_IMG_IMBALANCE
            reasons.append(f"图片占比过高(每图仅摊 {words_per_image:.0f} 字)")
    dup_groups = _duplicate_groups(extracted.paragraphs)
    if dup_groups:
        dup_penalty = min(PENALTY_DUPLICATE_CAP, dup_groups * PENALTY_DUPLICATE_PER_GROUP)
        penalty += dup_penalty
        reasons.append(f"存在重复段落({dup_groups} 组)")

    score = max(0, min(100, length_score + meta_score + structure_score - penalty))
    passed = score >= QUALITY_PASS_THRESHOLD
    if not passed:
        reasons.insert(0, f"总分 {score} 低于及格线 {QUALITY_PASS_THRESHOLD}")
    return QualityVerdict(score=score, passed=passed, reasons=reasons)
