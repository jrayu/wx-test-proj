# Lofter Tag Monitor

A Python bot that monitors a user-specified tag on [Lofter](https://www.lofter.com),
collects threads and comments that may spark fights or violate community guidelines,
and generates an **hourly Markdown summary report** for admin review.

---

## Features

| Feature | Detail |
|---|---|
| 🔍 Tag scraping | Fetches recent threads and comments for any Lofter tag |
| ⚠️ Fight-risk detection | Keyword & pattern heuristics for insults, threats, hate speech, doxxing, fandom wars |
| 📊 Hourly reports | Timestamped Markdown files sorted by risk score |
| 🔁 Scheduler | Runs automatically every hour; also supports a single-run mode |
| 🧪 Tests | 29 unit tests covering the analyser and reporter |

---

## Requirements

- Python 3.9+
- Dependencies listed in `requirements.txt`

```bash
pip install -r requirements.txt
```

---

## Usage

### Continuous monitoring (hourly)

```bash
python main.py --tag 原神
```

The bot will:
1. Immediately scrape the tag and produce an initial report.
2. Repeat every 60 minutes, saving a new `.md` file to `reports/` each time.

### Single run

```bash
python main.py --tag 原神 --once
```

### Custom output directory

```bash
python main.py --tag 原神 --output-dir /var/log/lofter-reports
```

### All options

```
usage: main.py [-h] --tag TAG [--output-dir DIR] [--once] [--delay SECONDS]

options:
  --tag TAG          Lofter tag to monitor (e.g. '原神')
  --output-dir DIR   Directory where Markdown reports are saved (default: reports/)
  --once             Run a single monitoring cycle and exit
  --delay SECONDS    Delay between HTTP requests to avoid rate-limiting (default: 1.0s)
```

---

## Report format

Each hourly report is saved as `reports/report_<tag>_<YYYYMMDD_HHMM>.md`.

```
# Lofter Tag Monitor — Hourly Report

| Field | Value |
|---|---|
| Tag | `#原神` |
| Period | 2024-06-01 10:00 → 2024-06-01 11:00 (UTC) |
| Flagged posts | 3 |
| Flagged items (posts + comments) | 7 |

## Summary — Posts Requiring Attention

| # | Author | Title / Snippet | Risk Score | Signals | URL |
|---|---|---|---|---|---|
| 1 | user_x | 你这个脑残废物…  | **9.0** | personal_attack, threat | https://… |
...

## Detailed Entries
...

## Recommended Actions
1. Review each flagged entry at the URL provided.
2. Warn / mute the author or remove the post via the admin panel.
3. High-score entries (≥ 8.0) should be prioritised for immediate review.
```

---

## Fight-risk signals detected

| Signal | Examples |
|---|---|
| `personal_attack` | 脑残, 傻逼, 废物, go die |
| `threat` | 人肉, 举报, 弄死你 |
| `hate_speech` | 直男癌, 地域歧视 |
| `fandom_war` | 撕逼, 脑残粉, 控评, 互撕 |
| `doxxing` | phone numbers, ID card numbers |
| `escalation` | 你算什么东西, 你行你上, 连续感叹号/问号 |

---

## Project structure

```
lofter_bot/
├── scraper.py      # Fetches posts & comments from Lofter tag pages
├── analyzer.py     # Detects fight-risk content, assigns scores
├── reporter.py     # Generates Markdown summary reports
└── scheduler.py    # Runs the pipeline hourly via `schedule`
main.py             # CLI entry point
tests/
├── test_analyzer.py
└── test_reporter.py
requirements.txt
```

---

## Running tests

```bash
pip install pytest
python -m pytest tests/ -v
```
