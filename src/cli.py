from __future__ import annotations

import argparse


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search and rank Phase One European jobs")
    parser.add_argument("--dry-run", action="store_true", help="Generate a report without email or Sheets writes")
    parser.add_argument("--no-email", action="store_true", help="Do not send email")
    parser.add_argument("--no-sheets", action="store_true", help="Use local SQLite only")
    return parser.parse_args(argv)
