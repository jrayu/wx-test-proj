"""Hourly report generator.

Takes the flagged :class:`PostAnalysis` results for a one-hour window and
produces a human-readable Markdown summary that admins can act on.
"""

from __future__ import annotations

import textwrap
from datetime import datetime, timezone
from typing import List, Sequence

from .analyzer import PostAnalysis

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_report(
    tag: str,
    analyses: Sequence[PostAnalysis],
    period_start: datetime,
    period_end: datetime,
) -> str:
    """Build a Markdown admin-report for a one-hour monitoring window.

    Parameters
    ----------
    tag:
        The Lofter tag that was monitored.
    analyses:
        All :class:`PostAnalysis` objects that contain at least one flagged
        item (post body or comment).
    period_start / period_end:
        The UTC time range covered by this report.

    Returns
    -------
    str
        A Markdown-formatted report string ready for display or storage.
    """
    now_str = _fmt(datetime.now(tz=timezone.utc))
    start_str = _fmt(period_start)
    end_str = _fmt(period_end)

    flagged_posts = [a for a in analyses if a.any_flagged]
    total_flagged_items = sum(a.flagged_count for a in flagged_posts)

    lines: List[str] = []

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------
    lines += [
        f"# Lofter Tag Monitor — Hourly Report",
        f"",
        f"| Field | Value |",
        f"|---|---|",
        f"| Tag | `#{tag}` |",
        f"| Period | {start_str} → {end_str} (UTC) |",
        f"| Generated at | {now_str} UTC |",
        f"| Flagged posts | {len(flagged_posts)} |",
        f"| Flagged items (posts + comments) | {total_flagged_items} |",
        f"",
    ]

    if not flagged_posts:
        lines += [
            "> ✅ No fight-risk content detected during this period.",
            "",
            "## Recommended Actions",
            "",
            "No action required for this period.",
            "",
            "_This report was generated automatically by the Lofter Tag Monitor bot._",
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Summary table — sorted by max score descending
    # ------------------------------------------------------------------
    lines += [
        "## Summary — Posts Requiring Attention",
        "",
        "| # | Author | Title / Snippet | Risk Score | Signals | URL |",
        "|---|---|---|---|---|---|",
    ]
    sorted_posts = sorted(flagged_posts, key=lambda a: a.max_score, reverse=True)
    for rank, analysis in enumerate(sorted_posts, 1):
        post = analysis.post
        title = _truncate(post.title or post.content, 40)
        signals = ", ".join(analysis.post_result.signals) or "—"
        url = post.url or "N/A"
        lines.append(
            f"| {rank} | {post.author} | {title} "
            f"| **{analysis.max_score:.1f}** | {signals} | {url} |"
        )

    lines += ["", ""]

    # ------------------------------------------------------------------
    # Detailed section per flagged post
    # ------------------------------------------------------------------
    lines += ["## Detailed Entries", ""]
    for rank, analysis in enumerate(sorted_posts, 1):
        post = analysis.post
        lines += [
            f"### {rank}. {_truncate(post.title or post.content, 60)}",
            f"",
            f"- **Author:** {post.author}",
            f"- **URL:** {post.url or 'N/A'}",
            f"- **Published:** {_fmt(post.published_at) if post.published_at else 'unknown'}",
            f"- **Post risk score:** {analysis.post_result.score:.1f}",
            f"- **Signals:** {', '.join(analysis.post_result.signals) or 'none'}",
            f"",
        ]
        if analysis.post_result.flagged:
            lines += [
                "**Post excerpt:**",
                "",
                f"> {_truncate(analysis.post_result.text_snippet, 200)}",
                "",
            ]

        flagged_comments = [c for c in analysis.comment_results if c.flagged]
        if flagged_comments:
            lines += [
                f"**Flagged comments ({len(flagged_comments)}):**",
                "",
            ]
            for comment in flagged_comments:
                lines += [
                    f"- **{comment.author}** (score {comment.score:.1f},"
                    f" signals: {', '.join(comment.signals)}):",
                    f"  > {_truncate(comment.text_snippet, 150)}",
                    "",
                ]

        lines += ["---", ""]

    # ------------------------------------------------------------------
    # Recommendation footer
    # ------------------------------------------------------------------
    lines += [
        "## Recommended Actions",
        "",
        "1. Review each flagged entry at the URL provided.",
        "2. If content violates community guidelines, use the Lofter admin panel to",
        "   warn / mute the author or remove the post.",
        "3. High-score entries (≥ 8.0) should be prioritised for immediate review.",
        "",
        "_This report was generated automatically by the Lofter Tag Monitor bot._",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt(dt: datetime | None) -> str:
    if dt is None:
        return "N/A"
    return dt.strftime("%Y-%m-%d %H:%M")


def _truncate(text: str, length: int) -> str:
    text = text.replace("\n", " ").replace("|", "｜").strip()
    return text[:length] + "…" if len(text) > length else text
