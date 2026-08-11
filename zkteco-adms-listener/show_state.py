#!/usr/bin/env python3
import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent / "adms.sqlite3"


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    print("Latest request per path:")
    for row in cur.execute(
        """
        SELECT path, method, MAX(id) AS max_id
        FROM request_log
        GROUP BY path, method
        ORDER BY max_id DESC
        """
    ):
        print(row)

    print("\nRecent queued/sent/acked commands:")
    for row in cur.execute(
        """
        SELECT id, ts_created, ts_sent, sn, status, wire_id, raw_response, command_text
        FROM command_queue
        ORDER BY id DESC
        LIMIT 20
        """
    ):
        print(row)

    print("\nRecent command results:")
    for row in cur.execute(
        """
        SELECT id, ts, sn, cmd_id, return_code, cmd
        FROM command_results
        ORDER BY id DESC
        LIMIT 20
        """
    ):
        print(row)

    print("\nRecent fdata files:")
    for row in cur.execute(
        """
        SELECT id, ts, sn, pin, cmd, size_hint, file_path
        FROM fdata_files
        ORDER BY id DESC
        LIMIT 20
        """
    ):
        print(row)

    print("\nRecent querydata rows:")
    for row in cur.execute(
        """
        SELECT id, ts, sn, substr(raw_line, 1, 140)
        FROM querydata_raw
        ORDER BY id DESC
        LIMIT 20
        """
    ):
        print(row)


if __name__ == "__main__":
    main()
