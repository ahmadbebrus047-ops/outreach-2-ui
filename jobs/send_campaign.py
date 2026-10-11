#!/usr/bin/env python3
"""
Job 2: send the day's batch (new + due reminders) within the daily limit.
Run on a cron once per day. Handles both initial sends and the 7-day
reminders in a single pass so the daily cap is never exceeded.

Usage:
  python -m jobs.send_campaign            # real send via Gmail
  python -m jobs.send_campaign --dry-run  # print instead of sending
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.campaign import Campaign
from core.logging_setup import get_logger
from core.mailer import ConsoleMailer, GmailMailer

log = get_logger("send_campaign")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="log instead of sending")
    args = parser.parse_args()

    mailer = ConsoleMailer() if args.dry_run else GmailMailer()
    Campaign(mailer).run()


if __name__ == "__main__":
    main()
