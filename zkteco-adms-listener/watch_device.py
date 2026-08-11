#!/usr/bin/env python3
import argparse
import json
import sqlite3
import time
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent / "adms.sqlite3"


def render_row(row):
    row_id, ts, method, path, query_json, body = row
    query = json.loads(query_json)
    sn = query.get("SN")
    table = query.get("table")
    body_preview = body.strip().splitlines()[:1]
    head = body_preview[0] if body_preview else ""
    if len(head) > 100:
        head = head[:100] + "..."
    return f"{row_id} {ts} {method} {path} SN={sn} table={table} body='{head}'"


def main():
    parser = argparse.ArgumentParser(description="Tail ADMS request logs")
    parser.add_argument("--sn", help="Filter by device SN")
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    last_id = cur.execute("SELECT COALESCE(MAX(id), 0) FROM request_log").fetchone()[0]
    print(f"Watching request_log from id>{last_id} sn={args.sn or '*'}")

    while True:
        if args.sn:
            rows = cur.execute(
                """
                SELECT id, ts, method, path, query_json, body
                FROM request_log
                WHERE id > ? AND sn = ?
                ORDER BY id ASC
                """,
                (last_id, args.sn),
            ).fetchall()
        else:
            rows = cur.execute(
                """
                SELECT id, ts, method, path, query_json, body
                FROM request_log
                WHERE id > ?
                ORDER BY id ASC
                """,
                (last_id,),
            ).fetchall()
        for row in rows:
            print(render_row(row))
            last_id = row[0]
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
