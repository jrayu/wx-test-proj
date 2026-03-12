"""Content analyzer.

Evaluates posts and comments for content that is likely to spark conflict
(personal attacks, hate speech, aggressive language, etc.) and assigns each
a numeric *fight risk score* along with the matching signal labels.

The heuristics are intentionally simple and keyword-based so the bot works
without any external ML service.  The keyword lists focus on common
Chinese-language patterns seen in Lofter fandom disputes, but the
architecture is open to extension.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Sequence, Tuple

from .scraper import Comment, Post

# ---------------------------------------------------------------------------
# Signal keyword groups
# Each entry is (label, weight, [patterns]).
# Patterns are applied case-insensitively to the combined text.
# ---------------------------------------------------------------------------

_SIGNALS: List[Tuple[str, float, List[str]]] = [
    # --- Personal attacks / insults ---
    (
        "personal_attack",
        3.0,
        [
            r"傻[逼比屄]", r"蠢[货猪]", r"脑残", r"弱智", r"废物",
            r"滚[出去吧]", r"去死", r"死[全家]", r"你妈", r"妈的",
            r"fuck\s*you", r"idiot", r"stupid",
        ],
    ),
    # --- Threats / violence ---
    (
        "threat",
        4.0,
        [
            r"打[你你们死]", r"杀[了你]", r"弄死", r"揍你", r"举报",
            r"人肉", r"曝光", r"发[你的]地址", r"dox",
        ],
    ),
    # --- Hate / discrimination ---
    (
        "hate_speech",
        3.5,
        [
            r"[女男]权", r"田园[女权]", r"直男癌", r"lgb?t?\s*滚",
            r"地[域]黑", r"歧视", r"种族",
        ],
    ),
    # --- Fandom war / ship war triggers ---
    (
        "fandom_war",
        2.0,
        [
            r"脑残粉", r"毒唯", r"anti\b", r"黑粉", r"控评",
            r"撕[逼x]", r"互撕", r"粉圈", r"pick\s*战",
        ],
    ),
    # --- Doxxing / privacy ---
    (
        "doxxing",
        5.0,
        [
            r"[\d]{11}手机号", r"身份证[号码]?",
            # Chinese mobile numbers (11 digits starting with 1[3-9]).
            # Negative lookahead/lookbehind on digits prevents matching numbers
            # that are part of a longer sequence (e.g. 18-digit ID card numbers
            # or large prices), while still catching standalone phone numbers
            # surrounded by text, punctuation, or whitespace.
            r"(?<!\d)1[3-9]\d{9}(?!\d)",
            r"\d{17}[\dXx]",           # ID card number pattern
        ],
    ),
    # --- Aggressive escalation markers ---
    (
        "escalation",
        1.5,
        [
            r"你行你上", r"比烂", r"谁比谁", r"就你[们]?",
            r"你算什么", r"算什么东西",
            r"!!{2,}", r"！{2,}", r"\?{3,}", r"？{3,}",
        ],
    ),
]

# Score threshold above which a post/comment is flagged
FIGHT_THRESHOLD = 3.0


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class AnalysisResult:
    """Analysis outcome for a single piece of text (post or comment)."""

    item_id: str
    item_type: str          # "post" or "comment"
    author: str
    text_snippet: str       # first 120 chars of the analysed text
    score: float
    signals: List[str] = field(default_factory=list)
    flagged: bool = False
    post_url: str = ""

    def __post_init__(self) -> None:
        self.flagged = self.score >= FIGHT_THRESHOLD


@dataclass
class PostAnalysis:
    """Aggregated analysis for one post and all its comments."""

    post: Post
    post_result: AnalysisResult
    comment_results: List[AnalysisResult] = field(default_factory=list)

    @property
    def max_score(self) -> float:
        scores = [self.post_result.score] + [c.score for c in self.comment_results]
        return max(scores)

    @property
    def any_flagged(self) -> bool:
        return self.post_result.flagged or any(c.flagged for c in self.comment_results)

    @property
    def flagged_count(self) -> int:
        return (1 if self.post_result.flagged else 0) + sum(
            1 for c in self.comment_results if c.flagged
        )


# ---------------------------------------------------------------------------
# Analyser
# ---------------------------------------------------------------------------

# Pre-compile all patterns once.
_COMPILED_SIGNALS: List[Tuple[str, float, List[re.Pattern]]] = [
    (label, weight, [re.compile(p, re.IGNORECASE) for p in patterns])
    for label, weight, patterns in _SIGNALS
]


class ContentAnalyzer:
    """Analyses Lofter posts and comments for fight-risk signals."""

    def analyze_post(self, post: Post) -> PostAnalysis:
        """Return a :class:`PostAnalysis` for *post* and its comments."""
        post_result = self._analyze_text(
            item_id=post.post_id,
            item_type="post",
            author=post.author,
            text=f"{post.title} {post.content}",
            url=post.url,
        )
        comment_results = [
            self._analyze_text(
                item_id=f"{post.post_id}_c{c.comment_id}",
                item_type="comment",
                author=c.author,
                text=c.content,
                url=post.url,
            )
            for c in post.comments
        ]
        return PostAnalysis(
            post=post,
            post_result=post_result,
            comment_results=comment_results,
        )

    def analyze_posts(self, posts: Sequence[Post]) -> List[PostAnalysis]:
        """Analyse a list of posts and return only those with any flagged content."""
        results: List[PostAnalysis] = []
        for post in posts:
            analysis = self.analyze_post(post)
            if analysis.any_flagged:
                results.append(analysis)
        return results

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _analyze_text(
        item_id: str,
        item_type: str,
        author: str,
        text: str,
        url: str = "",
    ) -> AnalysisResult:
        score = 0.0
        signals: List[str] = []
        for label, weight, patterns in _COMPILED_SIGNALS:
            for pattern in patterns:
                if pattern.search(text):
                    score += weight
                    if label not in signals:
                        signals.append(label)
                    break  # one match per label group is enough

        return AnalysisResult(
            item_id=item_id,
            item_type=item_type,
            author=author,
            text_snippet=text[:120],
            score=score,
            signals=signals,
            post_url=url,
        )
