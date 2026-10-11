#!/usr/bin/env python3
"""
Helper to honor opt-outs. When someone replies UNSUBSCRIBE, run:
  python -m jobs.suppress their@email.com "opted out"
They'll never be emailed or re-added again.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.repository import SuppressionRepository


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python -m jobs.suppress <email> [reason]")
        raise SystemExit(1)
    email = sys.argv[1].strip().lower()
    reason = sys.argv[2] if len(sys.argv) > 2 else "manual opt-out"
    SuppressionRepository().add("email:" + email, email, reason)
    print(f"Suppressed {email}")


if __name__ == "__main__":
    main()
