#!/usr/bin/env python3
import argparse
import shlex
import subprocess
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
QUEUE_CMD = BASE_DIR / "queue_command.py"


def queue(sn: str, command: str) -> None:
    subprocess.run(
        [
            "python3",
            str(QUEUE_CMD),
            "--sn",
            sn,
            "--cmd",
            command,
        ],
        check=True,
    )


def normalize_tabs(value: str) -> str:
    return value.replace("\\t", "\t")


def build_user(pin: str, name: str, card_no: str, password: str, privilege: str) -> str:
    return (
        f"DATA UPDATE user "
        f"Pin={pin}\t"
        f"CardNo={card_no}\t"
        f"Password={password}\t"
        f"Name={name}\t"
        f"Group=1\t"
        f"Privilege={privilege}\t"
    )


def build_extuser(pin: str, first_name: str) -> str:
    return f"DATA UPDATE extuser Pin={pin}\tFirstName={first_name}\t"


def build_userauthorize(pin: str, tz_id: str, door_id: str) -> str:
    return (
        f"DATA UPDATE userauthorize "
        f"Pin={pin}\t"
        f"AuthorizeTimezoneId={tz_id}\t"
        f"AuthorizeDoorId={door_id}\t"
    )


def build_query(table: str) -> str:
    return f"DATA QUERY tablename={table},fielddesc=*,filter=*"


def main() -> None:
    parser = argparse.ArgumentParser(description="Queue Rodrigo-style ADMS commands")
    parser.add_argument("--sn", required=True, help="Device serial number")

    sub = parser.add_subparsers(dest="action", required=True)

    add_user = sub.add_parser("add-user", help="Queue DATA UPDATE user")
    add_user.add_argument("--pin", required=True)
    add_user.add_argument("--name", required=True)
    add_user.add_argument("--card-no", default="0")
    add_user.add_argument("--password", default="")
    add_user.add_argument("--privilege", default="0")

    add_ext = sub.add_parser("add-extuser", help="Queue DATA UPDATE extuser")
    add_ext.add_argument("--pin", required=True)
    add_ext.add_argument("--first-name", required=True)

    add_auth = sub.add_parser("add-userauth", help="Queue DATA UPDATE userauthorize")
    add_auth.add_argument("--pin", required=True)
    add_auth.add_argument("--timezone-id", default="1")
    add_auth.add_argument("--door-id", default="15")

    query = sub.add_parser("query", help="Queue DATA QUERY tablename=...")
    query.add_argument(
        "--table",
        required=True,
        choices=[
            "user",
            "transaction",
            "templatev10",
            "biophoto",
            "facev7",
            "extuser",
            "userauthorize",
        ],
    )

    raw = sub.add_parser("raw", help="Queue a raw command")
    raw.add_argument("--cmd", required=True, help="Raw command text (use \\t for tabs)")

    args = parser.parse_args()

    if args.action == "add-user":
        cmd = build_user(args.pin, args.name, args.card_no, args.password, args.privilege)
        queue(args.sn, cmd)
    elif args.action == "add-extuser":
        cmd = build_extuser(args.pin, args.first_name)
        queue(args.sn, cmd)
    elif args.action == "add-userauth":
        cmd = build_userauthorize(args.pin, args.timezone_id, args.door_id)
        queue(args.sn, cmd)
    elif args.action == "query":
        cmd = build_query(args.table)
        queue(args.sn, cmd)
    else:
        cmd = normalize_tabs(args.cmd)
        queue(args.sn, cmd)

    print("queued:", shlex.quote(cmd))


if __name__ == "__main__":
    main()
