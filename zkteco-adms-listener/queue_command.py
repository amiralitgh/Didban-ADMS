#!/usr/bin/env python3
import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent / "adms.sqlite3"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> None:
    parser = argparse.ArgumentParser(description="Queue a command for device polling /iclock/getrequest")
    parser.add_argument("--sn", required=True, help="Device serial number (SN)")
    parser.add_argument("--cmd", required=True, help="Raw command text to return to device")
    args = parser.parse_args()

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO command_queue(ts_created, sn, command_text, status)
            VALUES (?, ?, ?, 'queued')
            """,
            (utc_now(), args.sn, args.cmd),
        )
        conn.commit()
    print("queued")


if __name__ == "__main__":
    main()
