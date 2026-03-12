"""Hourly monitoring scheduler.

Wires the scraper, analyser, and reporter together and runs the pipeline
once per hour (or on demand).  Results are written to a configurable output
directory as timestamped Markdown files.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import schedule

from .analyzer import ContentAnalyzer
from .reporter import generate_report
from .scraper import LofterScraper

logger = logging.getLogger(__name__)

_DEFAULT_OUTPUT_DIR = Path("reports")


class MonitorScheduler:
    """Runs the scrape → analyse → report pipeline on a 1-hour cadence.

    Parameters
    ----------
    tag:
        The Lofter tag to monitor.
    output_dir:
        Directory where Markdown reports are saved.
    request_delay:
        Seconds between individual HTTP requests inside the scraper.
    """

    def __init__(
        self,
        tag: str,
        output_dir: Path = _DEFAULT_OUTPUT_DIR,
        request_delay: float = 1.0,
    ) -> None:
        self.tag = tag
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._scraper = LofterScraper(tag=tag, request_delay=request_delay)
        self._analyzer = ContentAnalyzer()
        self._last_run: Optional[datetime] = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run_once(self) -> Optional[Path]:
        """Execute one monitoring cycle and return the path of the saved report.

        Returns ``None`` when no report file was written (e.g. no content
        was fetched at all).
        """
        period_end = datetime.now(tz=timezone.utc)
        period_start = self._last_run or (period_end - timedelta(hours=1))

        logger.info(
            "Running monitoring cycle for tag '%s' (%s → %s)",
            self.tag,
            period_start.strftime("%H:%M"),
            period_end.strftime("%H:%M"),
        )

        posts = self._scraper.fetch_posts_with_comments(since=period_start)
        logger.info("Fetched %d posts", len(posts))

        analyses = self._analyzer.analyze_posts(posts)
        logger.info("%d posts contain flagged content", len(analyses))

        report_md = generate_report(
            tag=self.tag,
            analyses=analyses,
            period_start=period_start,
            period_end=period_end,
        )

        report_path = self._save_report(report_md, period_end)
        self._last_run = period_end

        # Print a concise summary to stdout so the operator knows something
        # happened even without inspecting the file.
        flagged = sum(a.flagged_count for a in analyses)
        print(
            f"[{period_end.strftime('%Y-%m-%d %H:%M UTC')}] "
            f"Tag #{self.tag} — {len(posts)} posts scanned, "
            f"{len(analyses)} flagged threads, "
            f"{flagged} total flagged items. "
            f"Report: {report_path}"
        )
        return report_path

    def start(self) -> None:
        """Block and run the monitoring pipeline every hour."""
        logger.info("Starting hourly monitor for tag '#%s'.", self.tag)

        # Run immediately on startup, then every hour.
        self.run_once()
        schedule.every(1).hours.do(self.run_once)

        while True:
            schedule.run_pending()
            time.sleep(30)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _save_report(self, content: str, ts: datetime) -> Path:
        filename = f"report_{self.tag}_{ts.strftime('%Y%m%d_%H%M')}.md"
        path = self.output_dir / filename
        path.write_text(content, encoding="utf-8")
        logger.info("Report saved to %s", path)
        return path
