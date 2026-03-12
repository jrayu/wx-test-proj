#!/usr/bin/env python3
"""Lofter Tag Monitor — entry point.

Usage
-----
    python main.py --tag <tag> [--output-dir reports] [--once] [--delay 1.0]

Examples
--------
    # Run continuously, generating an hourly report for tag "原神":
    python main.py --tag 原神

    # Run a single cycle and exit:
    python main.py --tag 原神 --once

    # Save reports to a custom directory:
    python main.py --tag 原神 --output-dir /var/log/lofter-reports
"""

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from lofter_bot.scheduler import MonitorScheduler

# Load optional .env file (e.g. for proxies or future auth tokens)
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Monitor a Lofter tag and generate hourly fight-risk reports.",
    )
    parser.add_argument(
        "--tag",
        required=True,
        help="Lofter tag to monitor (e.g. '原神').",
    )
    parser.add_argument(
        "--output-dir",
        default="reports",
        metavar="DIR",
        help="Directory where Markdown reports are saved (default: reports/).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single monitoring cycle and exit instead of looping hourly.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        metavar="SECONDS",
        help="Delay between HTTP requests to avoid rate-limiting (default: 1.0s).",
    )

    args = parser.parse_args()

    scheduler = MonitorScheduler(
        tag=args.tag,
        output_dir=Path(args.output_dir),
        request_delay=args.delay,
    )

    if args.once:
        report_path = scheduler.run_once()
        if report_path:
            print(f"\nReport written to: {report_path}")
        return 0

    scheduler.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
