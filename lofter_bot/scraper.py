"""Lofter tag scraper.

Fetches recent threads (posts) and their comments for a given tag using
Lofter's public web pages.  Each item is returned as a plain dict so that
the rest of the pipeline stays independent of any HTTP/HTML details.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlencode, quote

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Post:
    """A single Lofter thread (post) entry."""
    post_id: str
    author: str
    title: str
    content: str
    url: str
    tag: str
    published_at: Optional[datetime] = None
    comments: List["Comment"] = field(default_factory=list)


@dataclass
class Comment:
    """A comment attached to a :class:`Post`."""
    comment_id: str
    author: str
    content: str
    published_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.lofter.com/",
}

_TAG_URL = "https://www.lofter.com/tag/{tag}"
_TAG_API_URL = "https://www.lofter.com/taglist.api"


class LofterScraper:
    """Scrapes threads and comments for a Lofter tag.

    Parameters
    ----------
    tag:
        The Lofter tag to monitor (e.g. ``"原神"``).
    limit:
        Maximum number of posts to fetch per call (default 30).
    request_delay:
        Seconds to wait between HTTP requests to avoid rate-limiting (default 1).
    session:
        Optional pre-configured :class:`requests.Session` (useful for testing).
    """

    def __init__(
        self,
        tag: str,
        limit: int = 30,
        request_delay: float = 1.0,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.tag = tag
        self.limit = limit
        self.request_delay = request_delay
        self._session = session or requests.Session()
        self._session.headers.update(_DEFAULT_HEADERS)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_posts(self, since: Optional[datetime] = None) -> List[Post]:
        """Return recent posts for *self.tag*.

        Parameters
        ----------
        since:
            If given, only posts published on or after this time are returned.
        """
        posts = self._fetch_tag_page()
        if since:
            posts = [p for p in posts if p.published_at and p.published_at >= since]
        return posts

    def fetch_posts_with_comments(self, since: Optional[datetime] = None) -> List[Post]:
        """Return recent posts along with their comments."""
        posts = self.fetch_posts(since=since)
        for post in posts:
            try:
                post.comments = self._fetch_comments(post)
                time.sleep(self.request_delay)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to fetch comments for post %s: %s", post.post_id, exc)
        return posts

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, url: str, **kwargs) -> requests.Response:
        """Thin wrapper around session.get with basic error handling."""
        resp = self._session.get(url, timeout=15, **kwargs)
        resp.raise_for_status()
        return resp

    def _fetch_tag_page(self) -> List[Post]:
        """Fetch the first page of posts for the tag from Lofter."""
        url = _TAG_URL.format(tag=quote(self.tag))
        try:
            resp = self._get(url)
        except requests.RequestException as exc:
            logger.error("Failed to fetch tag page for '%s': %s", self.tag, exc)
            return []

        return self._parse_tag_page(resp.text)

    def _parse_tag_page(self, html: str) -> List[Post]:
        """Parse Lofter tag listing HTML into a list of :class:`Post` objects."""
        soup = BeautifulSoup(html, "html.parser")
        posts: List[Post] = []

        # Lofter tag pages render post items inside <div class="post"> blocks.
        # Each block contains a link to the full post.
        for idx, item in enumerate(soup.select(".post")[:self.limit]):
            try:
                post = self._parse_post_item(item, idx)
                if post:
                    posts.append(post)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Skipping unparseable post item: %s", exc)

        logger.info("Fetched %d posts for tag '%s'", len(posts), self.tag)
        return posts

    def _parse_post_item(self, item: BeautifulSoup, idx: int) -> Optional[Post]:
        """Extract fields from a single post list-item element."""
        # --- URL / ID ---
        link_tag = item.select_one("a.ttl") or item.select_one("a[href]")
        url = link_tag["href"] if link_tag and link_tag.get("href") else ""
        post_id = url.split("/")[-1] if url else f"unknown_{idx}"

        # --- Author ---
        author_tag = item.select_one(".u-name") or item.select_one(".author")
        author = author_tag.get_text(strip=True) if author_tag else "unknown"

        # --- Title ---
        title_tag = item.select_one(".ttl") or item.select_one("h2") or item.select_one("h3")
        title = title_tag.get_text(strip=True) if title_tag else ""

        # --- Body text ---
        body_tag = item.select_one(".content") or item.select_one(".cnt") or item.select_one("p")
        content = body_tag.get_text(strip=True) if body_tag else ""

        # --- Published date ---
        time_tag = item.select_one("time") or item.select_one(".date") or item.select_one(".time")
        published_at: Optional[datetime] = None
        if time_tag:
            raw = time_tag.get("datetime") or time_tag.get_text(strip=True)
            published_at = _parse_datetime(raw)

        if not url and not title and not content:
            return None

        return Post(
            post_id=post_id,
            author=author,
            title=title,
            content=content,
            url=url,
            tag=self.tag,
            published_at=published_at,
        )

    def _fetch_comments(self, post: Post) -> List[Comment]:
        """Fetch comments for *post* from its detail page."""
        if not post.url:
            return []
        try:
            resp = self._get(post.url)
        except requests.RequestException as exc:
            logger.warning("Cannot load post page '%s': %s", post.url, exc)
            return []

        return self._parse_comments(resp.text)

    def _parse_comments(self, html: str) -> List[Comment]:
        """Extract comment entries from a post detail page."""
        soup = BeautifulSoup(html, "html.parser")
        comments: List[Comment] = []
        for idx, item in enumerate(soup.select(".comment-item, .cmt-item, .reply")):
            try:
                author_tag = item.select_one(".name, .author, .u-name")
                author = author_tag.get_text(strip=True) if author_tag else "unknown"
                body_tag = item.select_one(".content, .cnt, p")
                content = body_tag.get_text(strip=True) if body_tag else item.get_text(strip=True)
                time_tag = item.select_one("time, .date, .time")
                raw_dt = time_tag.get("datetime", "") or (time_tag.get_text(strip=True) if time_tag else "")
                comments.append(Comment(
                    comment_id=f"{idx}",
                    author=author,
                    content=content,
                    published_at=_parse_datetime(raw_dt) if raw_dt else None,
                ))
            except Exception as exc:  # noqa: BLE001
                logger.debug("Skipping comment: %s", exc)
        return comments


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _parse_datetime(raw: str) -> Optional[datetime]:
    """Best-effort parse of a datetime string from Lofter HTML."""
    if not raw:
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(raw.strip(), fmt)
        except ValueError:
            continue
    return None
