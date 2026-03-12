"""Unit tests for lofter_bot.analyzer."""

import pytest

from lofter_bot.analyzer import (
    FIGHT_THRESHOLD,
    ContentAnalyzer,
    PostAnalysis,
)
from lofter_bot.scraper import Comment, Post


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_post(
    content: str = "",
    title: str = "",
    post_id: str = "p1",
    comments: list[Comment] | None = None,
) -> Post:
    return Post(
        post_id=post_id,
        author="test_user",
        title=title,
        content=content,
        url="https://www.lofter.com/post/1",
        tag="test",
        comments=comments or [],
    )


def _make_comment(content: str, comment_id: str = "c1") -> Comment:
    return Comment(comment_id=comment_id, author="commenter", content=content)


# ---------------------------------------------------------------------------
# ContentAnalyzer.analyze_post
# ---------------------------------------------------------------------------

class TestAnalyzePost:
    def test_clean_post_not_flagged(self):
        post = _make_post(content="今天天气真好，大家一起讨论一下新番吧！")
        analyzer = ContentAnalyzer()
        result = analyzer.analyze_post(post)
        assert not result.post_result.flagged
        assert result.post_result.score < FIGHT_THRESHOLD

    def test_personal_attack_in_content_flagged(self):
        post = _make_post(content="你真是个脑残，连这个都不懂！")
        analyzer = ContentAnalyzer()
        result = analyzer.analyze_post(post)
        assert result.post_result.flagged
        assert "personal_attack" in result.post_result.signals

    def test_personal_attack_in_title_flagged(self):
        post = _make_post(title="傻逼粉丝滚出去", content="正文内容")
        analyzer = ContentAnalyzer()
        result = analyzer.analyze_post(post)
        assert result.post_result.flagged

    def test_threat_signal(self):
        post = _make_post(content="我要人肉你，把你的地址发出去！")
        analyzer = ContentAnalyzer()
        result = analyzer.analyze_post(post)
        assert result.post_result.flagged
        signals = result.post_result.signals
        # Should trigger at least threat or doxxing
        assert any(s in signals for s in ("threat", "doxxing"))

    def test_fandom_war_signal(self):
        post = _make_post(content="那些脑残粉整天撕逼，烦死了！")
        analyzer = ContentAnalyzer()
        result = analyzer.analyze_post(post)
        assert result.any_flagged
        assert "fandom_war" in result.post_result.signals or result.post_result.flagged

    def test_escalation_signal(self):
        post = _make_post(content="你算什么东西！！！！！")
        analyzer = ContentAnalyzer()
        result = analyzer.analyze_post(post)
        # Multiple escalation hits should push over threshold
        assert result.post_result.score > 0

    def test_flagged_comment_triggers_any_flagged(self):
        clean_post = _make_post(content="今天的动漫更新了！")
        bad_comment = _make_comment("废物，你这种人去死吧！")
        clean_post.comments = [bad_comment]
        analyzer = ContentAnalyzer()
        result = analyzer.analyze_post(clean_post)
        assert not result.post_result.flagged, "Post itself should be clean"
        assert result.any_flagged, "Flagged comment should mark post analysis as flagged"
        assert result.flagged_count == 1

    def test_flagged_count_accumulates(self):
        post = _make_post(content="你这个脑残！")
        bad_comments = [
            _make_comment("傻逼！", comment_id="c1"),
            _make_comment("大家好", comment_id="c2"),          # clean
            _make_comment("去死吧废物！", comment_id="c3"),
        ]
        post.comments = bad_comments
        analyzer = ContentAnalyzer()
        result = analyzer.analyze_post(post)
        # post + 2 bad comments = 3 flagged
        assert result.flagged_count == 3

    def test_max_score_reflects_highest(self):
        post = _make_post(content="今天天气真好")
        dangerous_comment = _make_comment("我要人肉你，发你地址，身份证号")
        post.comments = [dangerous_comment]
        analyzer = ContentAnalyzer()
        result = analyzer.analyze_post(post)
        assert result.max_score > result.post_result.score


# ---------------------------------------------------------------------------
# ContentAnalyzer.analyze_posts — filtering
# ---------------------------------------------------------------------------

class TestAnalyzePosts:
    def test_only_flagged_posts_returned(self):
        posts = [
            _make_post(content="今天真开心", post_id="p1"),
            _make_post(content="你个脑残废物！", post_id="p2"),
            _make_post(content="分享一首歌", post_id="p3"),
        ]
        analyzer = ContentAnalyzer()
        results = analyzer.analyze_posts(posts)
        assert len(results) == 1
        assert results[0].post.post_id == "p2"

    def test_empty_list_returns_empty(self):
        analyzer = ContentAnalyzer()
        assert analyzer.analyze_posts([]) == []

    def test_all_clean_returns_empty(self):
        posts = [_make_post(content="今天天气好", post_id=f"p{i}") for i in range(5)]
        analyzer = ContentAnalyzer()
        assert analyzer.analyze_posts(posts) == []


# ---------------------------------------------------------------------------
# Signal specifics
# ---------------------------------------------------------------------------

class TestSignals:
    def setup_method(self):
        self.analyzer = ContentAnalyzer()

    def _score(self, text: str) -> tuple[float, list[str]]:
        post = _make_post(content=text)
        r = self.analyzer.analyze_post(post)
        return r.post_result.score, r.post_result.signals

    def test_hate_speech_detected(self):
        score, signals = self._score("这种直男癌真的让人受不了")
        assert "hate_speech" in signals

    def test_doxxing_phone_number(self):
        score, signals = self._score("他的手机号是13812345678，大家去骚扰他！")
        assert "doxxing" in signals

    def test_multiple_signal_groups_accumulate_score(self):
        combined = "脑残废物，我要人肉你，发你地址！"
        score_combined, signals = self._score(combined)
        score_single, _ = self._score("脑残废物")
        assert score_combined > score_single
        assert len(signals) >= 2
