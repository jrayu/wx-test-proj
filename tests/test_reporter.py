"""Unit tests for lofter_bot.reporter."""

from datetime import datetime, timezone

import pytest

from lofter_bot.analyzer import AnalysisResult, ContentAnalyzer, PostAnalysis
from lofter_bot.reporter import generate_report, _fmt, _truncate
from lofter_bot.scraper import Post


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_UTC = timezone.utc
_START = datetime(2024, 6, 1, 10, 0, tzinfo=_UTC)
_END = datetime(2024, 6, 1, 11, 0, tzinfo=_UTC)


def _make_post(post_id: str = "p1", content: str = "some content") -> Post:
    return Post(
        post_id=post_id,
        author="user_a",
        title="Test Post",
        content=content,
        url=f"https://www.lofter.com/post/{post_id}",
        tag="test",
        published_at=_START,
    )


def _make_flagged_analysis(post: Post, score: float = 5.0) -> PostAnalysis:
    post_result = AnalysisResult(
        item_id=post.post_id,
        item_type="post",
        author=post.author,
        text_snippet=post.content[:120],
        score=score,
        signals=["personal_attack"],
        post_url=post.url,
    )
    return PostAnalysis(post=post, post_result=post_result)


# ---------------------------------------------------------------------------
# generate_report
# ---------------------------------------------------------------------------

class TestGenerateReport:
    def test_no_flagged_items_produces_clean_report(self):
        report = generate_report("test", [], _START, _END)
        assert "✅" in report
        assert "No fight-risk content detected" in report

    def test_report_contains_tag(self):
        report = generate_report("原神", [], _START, _END)
        assert "原神" in report

    def test_report_contains_period(self):
        report = generate_report("test", [], _START, _END)
        assert "2024-06-01 10:00" in report
        assert "2024-06-01 11:00" in report

    def test_flagged_post_appears_in_report(self):
        post = _make_post(post_id="p42", content="脑残废物！")
        analysis = _make_flagged_analysis(post, score=6.0)
        report = generate_report("test", [analysis], _START, _END)
        assert "user_a" in report
        assert "p42" in report or "lofter.com/post/p42" in report

    def test_summary_table_present_for_flagged(self):
        post = _make_post()
        analysis = _make_flagged_analysis(post)
        report = generate_report("test", [analysis], _START, _END)
        assert "Summary" in report
        assert "Detailed" in report

    def test_recommended_actions_always_present(self):
        # Present even when empty
        report_empty = generate_report("test", [], _START, _END)
        assert "Recommended Actions" in report_empty

        post = _make_post()
        report_flagged = generate_report("test", [_make_flagged_analysis(post)], _START, _END)
        assert "Recommended Actions" in report_flagged

    def test_flagged_count_in_header(self):
        posts = [_make_post(post_id=f"p{i}") for i in range(3)]
        analyses = [_make_flagged_analysis(p, score=4.0) for p in posts]
        report = generate_report("test", analyses, _START, _END)
        assert "3" in report

    def test_multiple_posts_sorted_by_score_descending(self):
        posts = [_make_post(post_id=f"p{i}") for i in range(3)]
        # Scores: p0=3, p1=9, p2=6
        analyses = [
            _make_flagged_analysis(posts[0], score=3.0),
            _make_flagged_analysis(posts[1], score=9.0),
            _make_flagged_analysis(posts[2], score=6.0),
        ]
        report = generate_report("test", analyses, _START, _END)
        # p1 (score 9) should appear before p2 (score 6) before p0 (score 3)
        pos_p1 = report.find("lofter.com/post/p1")
        pos_p2 = report.find("lofter.com/post/p2")
        pos_p0 = report.find("lofter.com/post/p0")
        assert pos_p1 < pos_p2 < pos_p0

    def test_comment_signals_appear_in_report(self):
        post = _make_post()
        post_result = AnalysisResult(
            item_id="p1",
            item_type="post",
            author="author",
            text_snippet="clean post",
            score=0.0,
            signals=[],
            post_url=post.url,
        )
        bad_comment = AnalysisResult(
            item_id="p1_c0",
            item_type="comment",
            author="commenter_x",
            text_snippet="你脑残废物去死",
            score=6.0,
            signals=["personal_attack"],
            post_url=post.url,
        )
        analysis = PostAnalysis(
            post=post,
            post_result=post_result,
            comment_results=[bad_comment],
        )
        report = generate_report("test", [analysis], _START, _END)
        assert "commenter_x" in report
        assert "personal_attack" in report


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_truncate_short_text_unchanged(self):
        assert _truncate("hello", 20) == "hello"

    def test_truncate_long_text_adds_ellipsis(self):
        result = _truncate("a" * 50, 10)
        assert result.endswith("…")
        assert len(result) == 11  # 10 chars + ellipsis

    def test_truncate_replaces_pipes(self):
        result = _truncate("a|b|c", 20)
        assert "|" not in result
        assert "｜" in result

    def test_fmt_none_returns_na(self):
        assert _fmt(None) == "N/A"

    def test_fmt_datetime_formats_correctly(self):
        dt = datetime(2024, 6, 1, 10, 30, tzinfo=_UTC)
        assert _fmt(dt) == "2024-06-01 10:30"
