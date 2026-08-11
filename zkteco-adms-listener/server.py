#!/usr/bin/env python3
import argparse
import hashlib
import hmac
import csv
import io
import json
import os
import re
import secrets
import sqlite3
import time
import zipfile
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "adms.sqlite3"
UPLOAD_DIR = BASE_DIR / "uploads"
STATIC_DIR = BASE_DIR / "static"
BACKUP_SCHEMA_VERSION = 1
AUTH_COOKIE_NAME = "didban_session"
AUTH_SESSION_TTL_SECONDS = 8 * 60 * 60
AUTH_PBKDF2_ITERATIONS = 260_000
INITIAL_ADMIN_PASSWORD = os.environ.get("DIDBAN_ADMIN_PASSWORD", "").strip()
try:
    DEVICE_ONLINE_WINDOW_SECONDS = max(
        30,
        int(os.environ.get("DIDBAN_DEVICE_ONLINE_WINDOW_SECONDS", "90")),
    )
except ValueError:
    DEVICE_ONLINE_WINDOW_SECONDS = 90
ATTENDANCE_QUERY_COMMAND = (
    "DATA QUERY ATTLOG StartTime=2000-01-01 00:00:00\t"
    "EndTime=2099-12-31 23:59:59"
)
BACKUP_TABLES = {
    "devices": ["sn", "display_name", "first_seen", "last_seen", "last_ip", "last_path", "model", "firmware", "status"],
    "users": ["sn", "pin", "name", "privilege", "password", "card", "group_id", "tz", "verify", "raw", "updated_at"],
    "biometrics": ["id", "ts", "sn", "pin", "kind", "template_no", "raw_line"],
    "attendance_raw": ["id", "ts", "sn", "table_name", "stamp", "raw_line"],
    "querydata_raw": ["id", "ts", "sn", "raw_line"],
    "fdata_files": ["id", "ts", "sn", "pin", "cmd", "size_hint", "content_type", "file_path"],
    "request_log": ["id", "ts", "method", "path", "query_json", "body", "sn"],
    "command_queue": ["id", "ts_created", "ts_sent", "sn", "command_text", "status", "wire_id", "raw_response"],
    "command_results": ["id", "ts", "sn", "cmd_id", "return_code", "cmd", "raw_body"],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def effective_device_status(row: sqlite3.Row) -> str:
    stored_status = str(row["status"] or "unknown").strip().lower()
    last_path = str(row["last_path"] or "").strip().lower()
    if not last_path.startswith("/iclock/"):
        return "unknown" if stored_status == "online" else stored_status
    try:
        last_seen = datetime.fromisoformat(str(row["last_seen"]))
    except (TypeError, ValueError):
        return "unknown"
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    age_seconds = max(0.0, (datetime.now(timezone.utc) - last_seen).total_seconds())
    return "online" if age_seconds <= DEVICE_ONLINE_WINDOW_SECONDS else "offline"


def hash_operator_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        AUTH_PBKDF2_ITERATIONS,
    )
    return f"{salt.hex()}${digest.hex()}"


def verify_operator_password(password: str, encoded: str) -> bool:
    try:
        salt_hex, digest_hex = encoded.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        AUTH_PBKDF2_ITERATIONS,
    )
    return hmac.compare_digest(actual, expected)


def operator_setting(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute(
        "SELECT value FROM operator_settings WHERE key=?",
        (key,),
    ).fetchone()
    return str(row["value"]) if row else None


def set_operator_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO operator_settings(key, value)
        VALUES(?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """,
        (key, value),
    )


def ensure_operator_auth(conn: sqlite3.Connection) -> None:
    if not operator_setting(conn, "password_hash"):
        if not INITIAL_ADMIN_PASSWORD:
            raise RuntimeError(
                "DIDBAN_ADMIN_PASSWORD must be set before initializing operator authentication"
            )
        set_operator_setting(conn, "password_hash", hash_operator_password(INITIAL_ADMIN_PASSWORD))
    if not operator_setting(conn, "session_secret"):
        set_operator_setting(conn, "session_secret", secrets.token_hex(32))


def connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with connect_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS devices (
                sn TEXT PRIMARY KEY,
                display_name TEXT NOT NULL DEFAULT '',
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                last_ip TEXT,
                last_path TEXT,
                model TEXT,
                firmware TEXT,
                status TEXT NOT NULL DEFAULT 'unknown'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS operator_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS request_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                method TEXT NOT NULL,
                path TEXT NOT NULL,
                query_json TEXT NOT NULL,
                body TEXT NOT NULL,
                sn TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS command_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_created TEXT NOT NULL,
                ts_sent TEXT,
                sn TEXT NOT NULL,
                command_text TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                wire_id INTEGER,
                raw_response TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS command_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                sn TEXT,
                cmd_id INTEGER,
                return_code INTEGER,
                cmd TEXT,
                raw_body TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS attendance_raw (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                sn TEXT,
                table_name TEXT,
                stamp TEXT,
                raw_line TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS querydata_raw (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                sn TEXT,
                raw_line TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fdata_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                sn TEXT,
                pin TEXT,
                cmd TEXT,
                size_hint INTEGER,
                content_type TEXT,
                file_path TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                sn TEXT NOT NULL,
                pin TEXT NOT NULL,
                name TEXT NOT NULL DEFAULT '',
                privilege TEXT NOT NULL DEFAULT '',
                password TEXT NOT NULL DEFAULT '',
                card TEXT NOT NULL DEFAULT '',
                group_id TEXT NOT NULL DEFAULT '',
                tz TEXT NOT NULL DEFAULT '',
                verify TEXT NOT NULL DEFAULT '',
                raw TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                PRIMARY KEY (sn, pin)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS biometrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                sn TEXT NOT NULL,
                pin TEXT,
                kind TEXT NOT NULL,
                template_no TEXT,
                raw_line TEXT NOT NULL,
                UNIQUE(sn, pin, kind, template_no, raw_line)
            )
            """
        )
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(command_queue)")}
        if "wire_id" not in columns:
            conn.execute("ALTER TABLE command_queue ADD COLUMN wire_id INTEGER")
        if "raw_response" not in columns:
            conn.execute("ALTER TABLE command_queue ADD COLUMN raw_response TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_attendance_sn ON attendance_raw(sn, id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_querydata_sn ON querydata_raw(sn, id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_requests_sn ON request_log(sn, id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_commands_sn ON command_queue(sn, id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_biometrics_sn_pin ON biometrics(sn, pin, id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_name ON users(name)")
        ensure_operator_auth(conn)
        backfill_canonical_data(conn)
        conn.commit()


def normalize_query(query: dict) -> dict:
    normalized = {}
    for key, value in query.items():
        normalized[key.lower()] = value
    return normalized


def parse_fields(payload: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for token in re.split(r"[\t&\r\n]+|(?=\b[A-Za-z][A-Za-z0-9_]*=)", payload):
        token = token.strip()
        if not token or "=" not in token:
            continue
        key, value = token.split("=", 1)
        fields[key.strip().lower()] = value.strip()
    return fields


def parse_user_line(raw_line: str) -> dict | None:
    line = raw_line.strip()
    if not line.upper().startswith("USER "):
        return None
    fields = parse_fields(line[5:])
    pin = fields.get("pin")
    if not pin:
        return None
    return {
        "pin": pin,
        "name": fields.get("name", ""),
        "privilege": fields.get("pri", fields.get("privilege", "")),
        "password": fields.get("passwd", fields.get("password", "")),
        "card": fields.get("card", fields.get("cardno", "")),
        "group_id": fields.get("grp", fields.get("group", "")),
        "tz": fields.get("tz", ""),
        "verify": fields.get("verify", ""),
        "raw": raw_line,
    }


def parse_biometric_line(raw_line: str) -> dict | None:
    line = raw_line.strip()
    upper = line.upper()
    kind = None
    for prefix, name in (
        ("FP ", "fingerprint"),
        ("FACE ", "face"),
        ("FINGERPRINT ", "fingerprint"),
        ("FINGERVEIN ", "finger_vein"),
        ("PALM ", "palm"),
    ):
        if upper.startswith(prefix):
            kind = name
            break
    if not kind:
        return None
    fields = parse_fields(line.split(" ", 1)[1])
    return {
        "pin": fields.get("pin"),
        "kind": kind,
        "template_no": fields.get("fid", fields.get("index", fields.get("no", ""))),
        "template": fields.get("tmp", fields.get("template", "")),
        "raw": raw_line,
    }


def upsert_user(conn: sqlite3.Connection, sn: str, user: dict) -> None:
    conn.execute(
        """
        INSERT INTO users(sn, pin, name, privilege, password, card, group_id, tz, verify, raw, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(sn, pin) DO UPDATE SET
            name=excluded.name,
            privilege=excluded.privilege,
            password=excluded.password,
            card=excluded.card,
            group_id=excluded.group_id,
            tz=excluded.tz,
            verify=excluded.verify,
            raw=excluded.raw,
            updated_at=excluded.updated_at
        """,
        (
            sn,
            user["pin"],
            user.get("name", ""),
            user.get("privilege", ""),
            user.get("password", ""),
            user.get("card", ""),
            user.get("group_id", ""),
            user.get("tz", ""),
            user.get("verify", ""),
            user.get("raw", ""),
            utc_now(),
        ),
    )


def store_canonical_line(conn: sqlite3.Connection, sn: str, raw_line: str) -> None:
    user = parse_user_line(raw_line)
    if user:
        upsert_user(conn, sn, user)
    biometric = parse_biometric_line(raw_line)
    if biometric:
        conn.execute(
            """
            INSERT OR IGNORE INTO biometrics(ts, sn, pin, kind, template_no, raw_line)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                utc_now(),
                sn,
                biometric["pin"],
                biometric["kind"],
                biometric["template_no"],
                biometric["raw"],
            ),
        )


def backfill_canonical_data(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT sn, raw_line FROM attendance_raw WHERE sn IS NOT NULL ORDER BY id ASC"
    ).fetchall()
    for row in rows:
        store_canonical_line(conn, row["sn"], row["raw_line"])
    rows = conn.execute(
        "SELECT sn, raw_line FROM querydata_raw WHERE sn IS NOT NULL ORDER BY id ASC"
    ).fetchall()
    for row in rows:
        store_canonical_line(conn, row["sn"], row["raw_line"])


def touch_device(
    conn: sqlite3.Connection,
    sn: str | None,
    path: str,
    client_ip: str,
    query: dict,
) -> None:
    if not sn:
        return
    now = utc_now()
    device_model = str(query.get("model", query.get("v", "")))
    firmware = str(query.get("firmware", query.get("fw", "")))
    conn.execute(
        """
        INSERT INTO devices(sn, first_seen, last_seen, last_ip, last_path, model, firmware, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'online')
        ON CONFLICT(sn) DO UPDATE SET
            last_seen=excluded.last_seen,
            last_ip=excluded.last_ip,
            last_path=excluded.last_path,
            model=CASE WHEN excluded.model <> '' THEN excluded.model ELSE devices.model END,
            firmware=CASE WHEN excluded.firmware <> '' THEN excluded.firmware ELSE devices.firmware END,
            status='online'
        """,
        (sn, now, now, client_ip, path, device_model, firmware),
    )


def write_request_log(
    conn: sqlite3.Connection,
    method: str,
    path: str,
    query: dict,
    body: str,
    sn: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO request_log(ts, method, path, query_json, body, sn)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (utc_now(), method, path, json.dumps(query), body, sn),
    )


def insert_queued_command(conn: sqlite3.Connection, sn: str, command_text: str) -> int:
    cursor = conn.execute(
        """
        INSERT INTO command_queue(ts_created, sn, command_text, status)
        VALUES (?, ?, ?, 'queued')
        """,
        (utc_now(), sn, command_text),
    )
    return int(cursor.lastrowid)


def userinfo_update_command(
    pin: str,
    name: str,
    privilege: str = "0",
    password: str = "",
    card: str = "",
    group_id: str = "1",
    tz: str = "0001000100000000",
    verify: str = "0",
) -> str:
    return (
        f"DATA UPDATE USERINFO PIN={pin}\tName={name}\tPri={privilege}\t"
        f"Passwd={password}\tCard={card}\tGrp={group_id}\tTZ={tz}\tVerify={verify}"
    )


def user_update_command(
    pin: str,
    name: str,
    privilege: str = "0",
    password: str = "",
    card: str = "0",
    group_id: str = "1",
) -> str:
    return (
        f"DATA UPDATE user Pin={pin}\tCardNo={card}\tPassword={password}\t"
        f"Name={name}\tGroup={group_id}\tPrivilege={privilege}\t"
    )


def build_user_commands(user: dict, dual_mode: bool = True) -> list[str]:
    commands = [
        userinfo_update_command(
            pin=str(user.get("pin", "")).strip(),
            name=str(user.get("name", "")).strip(),
            privilege=str(user.get("privilege", "0")).strip(),
            password=str(user.get("password", "")).strip(),
            card=str(user.get("card", "")).strip(),
            group_id=str(user.get("group_id", user.get("group", "1"))).strip(),
            tz=str(user.get("tz", "0001000100000000")).strip(),
            verify=str(user.get("verify", "0")).strip(),
        )
    ]
    if dual_mode:
        commands.append(
            user_update_command(
                pin=str(user.get("pin", "")).strip(),
                name=str(user.get("name", "")).strip(),
                privilege=str(user.get("privilege", "0")).strip(),
                password=str(user.get("password", "")).strip(),
                card=str(user.get("card", "0")).strip() or "0",
                group_id=str(user.get("group_id", user.get("group", "1"))).strip(),
            )
        )
    return commands


def biometric_command(payload: dict) -> str:
    raw_command = str(payload.get("command", "")).strip()
    if raw_command:
        return raw_command
    pin = str(payload.get("pin", "")).strip()
    template = str(payload.get("template", "")).strip()
    template_no = str(payload.get("template_no", payload.get("fid", "0"))).strip()
    kind = str(payload.get("kind", "fingerprint")).strip().lower()
    if not pin or not template:
        raise ValueError("pin and template are required")
    if kind in {"face", "facev7"}:
        table = "facev7"
    elif kind in {"fingerprint", "fp", "template", "templatev10"}:
        table = "templatev10"
    else:
        table = kind
    return (
        f"DATA UPDATE {table} PIN={pin}\tFID={template_no}\tValid=1\t"
        f"TMP={template}"
    )


def clean_device_sn(value: object) -> str:
    sn = str(value or "").strip()
    if not sn:
        return ""
    if any(ord(character) < 32 for character in sn):
        raise ValueError("sn must not contain control characters")
    return sn


def device_sn_values(value: object) -> list[str]:
    values = value if isinstance(value, list) else [value]
    result: list[str] = []
    for item in values:
        for candidate in str(item or "").split(","):
            cleaned = clean_device_sn(candidate)
            if cleaned and cleaned not in result:
                result.append(cleaned)
    return result


def requested_device_sns(query: dict, *keys: str) -> list[str]:
    values: list[str] = []
    for key in keys or ("sns", "sn"):
        if key in query:
            values.extend(device_sn_values(query.get(key)))
    return list(dict.fromkeys(values))


def parse_filter_datetime(value: object, end_of_day: bool = False) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        text = f"{text} {'23:59:59' if end_of_day else '00:00:00'}"
    text = text.replace("/", "-").replace("T", " ")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def attendance_event_time(raw_line: str) -> tuple[str, datetime | None]:
    fields = parse_fields(raw_line)
    candidate = ""
    for key in ("datetime", "timestamp", "time", "date"):
        if fields.get(key):
            candidate = fields[key]
            break
    if not candidate:
        match = re.search(
            r"\b(20\d{2}[-/]\d{1,2}[-/]\d{1,2}(?:[ T]\d{1,2}:\d{2}(?::\d{2})?))\b",
            raw_line,
        )
        candidate = match.group(1) if match else ""
    if not candidate:
        for part in raw_line.split("\t"):
            if re.fullmatch(r"20\d{2}[-/]\d{1,2}[-/]\d{1,2}[ T]\d{1,2}:\d{2}(?::\d{2})?", part.strip()):
                candidate = part.strip()
                break
    return candidate, parse_filter_datetime(candidate)


def attendance_record_details(raw_line: str) -> dict[str, str]:
    parts = [part.strip() for part in raw_line.split("\t")]
    event_time, _ = attendance_event_time(raw_line)
    return {
        "pin": parts[0] if parts else "",
        "event_time": event_time,
        "status": parts[2] if len(parts) > 2 else "",
        "verify": parts[3] if len(parts) > 3 else "",
        "work_code": parts[4] if len(parts) > 4 else "",
    }


def as_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"", "0", "false", "no", "off"}


def backup_snapshot(conn: sqlite3.Connection) -> dict:
    tables = {}
    for table_name, columns in BACKUP_TABLES.items():
        rows = conn.execute(
            f"SELECT {','.join(columns)} FROM {table_name} ORDER BY rowid"
        ).fetchall()
        tables[table_name] = [dict(row) for row in rows]
    upload_entries = []
    for row in tables["fdata_files"]:
        original_path = Path(str(row.get("file_path") or ""))
        if not original_path.is_file():
            continue
        archive_path = f"uploads/{original_path.name}"
        row["file_path"] = archive_path
        upload_entries.append(
            {
                "archive_path": archive_path,
                "original_path": str(original_path),
                "size": original_path.stat().st_size,
            }
        )
    manifest_uploads = [
        {"archive_path": item["archive_path"], "size": item["size"]}
        for item in upload_entries
    ]
    device_sns = sorted({str(row["sn"]) for row in tables["devices"] if row.get("sn")})
    return {
        "manifest": {
            "format": "adms-device-backup",
            "schema_version": BACKUP_SCHEMA_VERSION,
            "created_at": utc_now(),
            "device_sns": device_sns,
            "table_counts": {name: len(rows) for name, rows in tables.items()},
            "upload_count": len(upload_entries),
            "uploads": manifest_uploads,
            "notes": [
                "The archive contains sensitive employee and biometric data.",
                "Historical attendance and raw traffic are retained for audit; they are not replayed to devices.",
                "Old command queue entries are retained for audit; they are not replayed during restore.",
            ],
        },
        "tables": tables,
        "uploads": upload_entries,
    }


def create_backup_zip(conn: sqlite3.Connection) -> bytes:
    snapshot = backup_snapshot(conn)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(snapshot["manifest"], ensure_ascii=False, indent=2),
        )
        for table_name, rows in snapshot["tables"].items():
            archive.writestr(
                f"data/{table_name}.json",
                json.dumps(rows, ensure_ascii=False, indent=2),
            )
        for upload in snapshot["uploads"]:
            original_path = Path(upload["original_path"])
            if original_path.is_file():
                archive.write(original_path, upload["archive_path"])
    return output.getvalue()


def read_backup_zip(raw_body: bytes) -> tuple[dict, list[dict], list[dict]]:
    if not raw_body:
        raise ValueError("Backup ZIP is empty")
    if len(raw_body) > 250 * 1024 * 1024:
        raise ValueError("Backup ZIP is larger than the 250 MB safety limit")
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw_body))
    except zipfile.BadZipFile as exc:
        raise ValueError("Uploaded file is not a valid ZIP backup") from exc
    names = set(archive.namelist())
    for name in names:
        path = Path(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name:
            raise ValueError(f"Unsafe path in backup ZIP: {name}")
    if "manifest.json" not in names:
        raise ValueError("Backup ZIP is missing manifest.json")
    try:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("manifest.json is not valid UTF-8 JSON") from exc
    if manifest.get("format") != "adms-device-backup":
        raise ValueError("This ZIP is not an ADMS device backup")
    if int(manifest.get("schema_version", 0)) != BACKUP_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported backup schema: {manifest.get('schema_version')}"
        )
    tables = {}
    issues = []
    warnings = []
    for table_name in BACKUP_TABLES:
        filename = f"data/{table_name}.json"
        if filename not in names:
            issues.append({"severity": "error", "code": "missing_table", "table": table_name})
            tables[table_name] = []
            continue
        try:
            value = json.loads(archive.read(filename).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            issues.append(
                {"severity": "error", "code": "invalid_table", "table": table_name, "message": str(exc)}
            )
            tables[table_name] = []
            continue
        if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
            issues.append({"severity": "error", "code": "table_not_list", "table": table_name})
            tables[table_name] = []
        else:
            tables[table_name] = value
    for upload in manifest.get("uploads", []):
        archive_path = str(upload.get("archive_path", ""))
        if archive_path and archive_path not in names:
            warnings.append(
                {
                    "severity": "warning",
                    "code": "missing_upload",
                    "path": archive_path,
                    "message": "The metadata exists but the uploaded payload is missing.",
                }
            )
    snapshot = {"manifest": manifest, "tables": tables, "archive_names": sorted(names)}
    return snapshot, issues, warnings


def inspect_backup_snapshot(snapshot: dict, known_sns: set[str]) -> dict:
    tables = snapshot["tables"]
    issues = []
    warnings = []
    users = {}
    users_by_pin = {}
    for row in tables.get("users", []):
        sn = str(row.get("sn", "")).strip()
        pin = str(row.get("pin", "")).strip()
        if not sn or not pin:
            issues.append({"severity": "error", "code": "user_missing_identity", "row": row})
            continue
        key = (sn, pin)
        if key in users and users[key] != row:
            issues.append(
                {
                    "severity": "error",
                    "code": "conflicting_user",
                    "sn": sn,
                    "pin": pin,
                    "message": "Two different employee records share the same device and PIN.",
                }
            )
        users[key] = row
        pin_signature = tuple(
            str(row.get(field, ""))
            for field in ("name", "privilege", "password", "card", "group_id", "tz", "verify")
        )
        previous_signature = users_by_pin.setdefault(pin, pin_signature)
        if previous_signature != pin_signature:
            warnings.append(
                {
                    "severity": "warning",
                    "code": "cross_device_user_difference",
                    "pin": pin,
                    "message": "The same PIN has different employee data across source devices.",
                }
            )
    source_sns = sorted(
        {
            str(row.get("sn", "")).strip()
            for row in tables.get("devices", [])
            if str(row.get("sn", "")).strip()
        }
        | {str(row.get("sn", "")).strip() for row in tables.get("users", []) if str(row.get("sn", "")).strip()}
        | {
            str(row.get("sn", "")).strip()
            for row in tables.get("biometrics", [])
            if str(row.get("sn", "")).strip()
        }
    )
    for sn in source_sns:
        if sn not in known_sns:
            warnings.append(
                {
                    "severity": "warning",
                    "code": "unknown_device",
                    "sn": sn,
                    "message": "The source serial is not currently connected to this server.",
                }
            )
    for row in tables.get("biometrics", []):
        sn = str(row.get("sn", "")).strip()
        pin = str(row.get("pin", "")).strip()
        if not sn or not pin:
            issues.append({"severity": "error", "code": "biometric_missing_identity", "row": row})
        elif (sn, pin) not in users:
            warnings.append(
                {
                    "severity": "warning",
                    "code": "biometric_without_user",
                    "sn": sn,
                    "pin": pin,
                    "message": "Biometric data has no matching employee record in the backup.",
                }
            )
        if str(row.get("kind", "")).lower() not in {"fingerprint", "face", "finger_vein", "palm", "file"}:
            warnings.append(
                {
                    "severity": "warning",
                    "code": "unsupported_biometric_kind",
                    "kind": row.get("kind"),
                    "sn": sn,
                    "pin": pin,
                }
            )
    if tables.get("fdata_files"):
        warnings.append(
            {
                "severity": "warning",
                "code": "uploaded_files_not_replayed",
                "message": "Uploaded photos/files are preserved in the ZIP but are not replayed to devices by ADMS restore.",
            }
        )
    return {
        "source_devices": source_sns,
        "known_devices": sorted(known_sns),
        "counts": {name: len(rows) for name, rows in tables.items()},
        "issues": issues,
        "warnings": warnings,
        "compatible": not any(item["severity"] == "error" for item in issues),
    }


def backup_restore_targets(source_sn: str, options: dict, known_sns: set[str]) -> list[str]:
    mapping = options.get("device_map", {})
    if isinstance(mapping, dict) and source_sn in mapping:
        raw_targets = mapping[source_sn]
        if isinstance(raw_targets, str):
            raw_targets = [raw_targets]
        if isinstance(raw_targets, list):
            candidates = list(
                dict.fromkeys(
                    clean_device_sn(target)
                    for target in raw_targets
                    if clean_device_sn(target)
                )
            )
            return [target for target in candidates if target in known_sns]
    mode = str(options.get("mode", "matching")).strip().lower()
    if mode == "all":
        return sorted(known_sns)
    if source_sn in known_sns:
        return [source_sn]
    return []


def queue_backup_restore(
    conn: sqlite3.Connection,
    snapshot: dict,
    options: dict,
    known_sns: set[str],
) -> dict:
    tables = snapshot["tables"]
    inspection = inspect_backup_snapshot(snapshot, known_sns)
    if not inspection["compatible"]:
        raise ValueError("Backup consistency errors must be resolved before restore")
    users_by_source: dict[str, dict[str, dict]] = {}
    for row in tables.get("users", []):
        source_sn = str(row.get("sn", "")).strip()
        pin = str(row.get("pin", "")).strip()
        users_by_source.setdefault(source_sn, {})[pin] = row
    biometrics_by_source: dict[str, list[dict]] = {}
    for row in tables.get("biometrics", []):
        source_sn = str(row.get("sn", "")).strip()
        biometrics_by_source.setdefault(source_sn, []).append(row)
    queued_targets = []
    warnings = list(inspection["warnings"])
    for source_sn, users in users_by_source.items():
        targets = backup_restore_targets(source_sn, options, known_sns)
        if not targets:
            warnings.append(
                {
                    "severity": "warning",
                    "code": "no_restore_target",
                    "sn": source_sn,
                    "message": "No connected target matched this source serial.",
                }
            )
            continue
        for target_sn in targets:
            target_user_count = 0
            target_biometric_count = 0
            command_ids = []
            for pin, user in users.items():
                user_commands = [
                    command
                    for command in build_user_commands(user, True)
                    if command.strip()
                ]
                for command in user_commands:
                    command_ids.append(insert_queued_command(conn, target_sn, command))
                target_user_count += 1
                for biometric in biometrics_by_source.get(source_sn, []):
                    if str(biometric.get("pin", "")).strip() != pin:
                        continue
                    parsed = parse_biometric_line(str(biometric.get("raw_line", "")))
                    if not parsed or not parsed.get("template"):
                        continue
                    if parsed.get("kind") not in {"fingerprint", "face"}:
                        continue
                    command = biometric_command(
                        {
                            "pin": pin,
                            "kind": parsed["kind"],
                            "template_no": parsed.get("template_no", ""),
                            "template": parsed["template"],
                        }
                    )
                    command_ids.append(insert_queued_command(conn, target_sn, command))
                    target_biometric_count += 1
            queued_targets.append(
                {
                    "source_sn": source_sn,
                    "target_sn": target_sn,
                    "users_queued": target_user_count,
                    "biometrics_queued": target_biometric_count,
                    "command_ids": command_ids,
                }
            )
    return {
        "targets": queued_targets,
        "warnings": warnings,
        "counts": inspection["counts"],
        "source_devices": inspection["source_devices"],
    }


def user_field_guide() -> list[dict]:
    return [
        {
            "field": "pin",
            "label": "Employee number",
            "meaning": "The number the device uses to identify the person.",
            "required": True,
            "safe_default": None,
        },
        {
            "field": "name",
            "label": "Full name",
            "meaning": "The name shown on the device and in attendance records.",
            "required": False,
            "safe_default": "",
        },
        {
            "field": "password",
            "label": "Device password",
            "meaning": "Optional numeric password for device verification. It is not the web-app password.",
            "required": False,
            "safe_default": "",
        },
        {
            "field": "card",
            "label": "Card number",
            "meaning": "Optional RFID/card number assigned to the employee.",
            "required": False,
            "safe_default": "",
        },
        {
            "field": "privilege",
            "label": "Device role",
            "meaning": "0 means ordinary employee. Higher values may grant device-management rights and should be used only when needed.",
            "required": False,
            "safe_default": "0",
        },
        {
            "field": "group_id",
            "label": "Device group",
            "meaning": "The device-side user group. Keep the default unless your device is configured with groups.",
            "required": False,
            "safe_default": "1",
        },
        {
            "field": "tz",
            "label": "Time-zone rule",
            "meaning": "The device access/time-zone value. Preserve the value received from the device when updating an existing user.",
            "required": False,
            "safe_default": "0001000100000000",
        },
        {
            "field": "verify",
            "label": "Verification mode",
            "meaning": "The device verification setting. Preserve the received value unless the device documentation says otherwise.",
            "required": False,
            "safe_default": "0",
        },
    ]


def operator_guide() -> dict:
    return {
        "title": "Simple ADMS operator guide",
        "device_identity": {
            "key": "sn",
            "label": "Device serial number",
            "meaning": "Every device is separated by its ADMS serial number. Never use IP address or PIN as the device identity.",
            "rule": "Every user, biometric, attendance row, request, and command must be targeted with the exact SN.",
        },
        "phases": [
            {
                "id": "connect",
                "number": 1,
                "title": "Connect devices",
                "goal": "Make every device visible, named, and receiving data.",
                "actions": [
                    "Configure the server IP and port on the device.",
                    "Wait for the device to appear in GET /api/devices.",
                    "Use POST /api/devices/{sn}/sync to request users and biometrics.",
                    "Give each device a friendly name and confirm its location.",
                ],
            },
            {
                "id": "manage",
                "number": 2,
                "title": "Manage and copy employees",
                "goal": "Create an employee once, then send the basic identity to selected devices.",
                "actions": [
                    "Choose one source device or create a new employee.",
                    "Use POST /api/users or PUT /api/users/{pin} for one device.",
                    "Use POST /api/users/copy with one source SN and explicit target SNs.",
                    'Use target_sns: "*" or "all" to copy to every known device.',
                    "Use POST /api/users/copy-many with a pins list for bulk operations.",
                    "Wait for a separate result for every target device.",
                ],
            },
            {
                "id": "operate",
                "number": 3,
                "title": "Reports, biometrics, and control",
                "goal": "Review attendance, handle biometric templates safely, and audit operations.",
                "actions": [
                    "Read attendance with GET /api/attendance?sn={sn}.",
                    "Query biometric templates with POST /api/biometrics/query.",
                    "Export biometrics with GET /api/biometrics/export.",
                    "Template writes are firmware-dependent; verify each target.",
                    "Every important action records who started it, when, and which devices.",
                    "Use GET /api/commands?sn={sn} to review command history.",
                    "Use GET /api/requests?sn={sn} to review raw ADMS traffic.",
                    "Plan for roles: local manager, office operator, biometric admin, read-only auditor.",
                ],
            },
        ],
        "user_fields": user_field_guide(),
        "workflows": {
            "create_user": {
                "request": "POST /api/users",
                "plain_language": "Add a person to one device. This queues the command; it does not enroll a new finger or face.",
                "next_step": "Enroll the biometric on the device, or copy an already stored template with POST /api/users/copy.",
            },
            "update_user": {
                "request": "PUT /api/users/{pin}",
                "plain_language": "Change the person's name, card, password, or device role on one device.",
            },
            "copy_user": {
                "request": "POST /api/users/copy",
                "plain_language": "Copy a known user from one device to selected known devices using the same PIN.",
                "safety": "Targets are explicit SNs; unknown targets are rejected instead of guessed.",
            },
            "biometrics": {
                "request": "POST /api/biometrics or POST /api/biometrics/query",
                "plain_language": "Retrieve stored templates or queue a template write.",
                "caveat": "Template write syntax and acceptance are firmware-dependent. Always verify with an ACK and a follow-up query.",
            },
        },
        "command_lifecycle": [
            {"status": "queued", "meaning": "Waiting for that exact device to poll the server."},
            {"status": "sent", "meaning": "Delivered in that device's ADMS response."},
            {"status": "acked", "meaning": "The device reported return code 0."},
            {"status": "error", "meaning": "The device returned a non-zero result or failed the command."},
        ],
        "important_limits": [
            "ADMS is HTTP push/poll; the server does not open a TCP session to the device.",
            "Creating a user does not magically capture a fingerprint or face.",
            "Do not grant device-management privilege to ordinary employees.",
            "A successful queue response means delivery is scheduled, not that the device mutation is already verified.",
        ],
    }


class ADMSHandler(BaseHTTPRequestHandler):
    server_version = "ADMSControl/1.0"

    def _session_token(self) -> str:
        cookies = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookies.get(AUTH_COOKIE_NAME)
        return morsel.value if morsel else ""

    def _is_authenticated(self) -> bool:
        token = self._session_token()
        if not token:
            return False
        with connect_db() as conn:
            secret = operator_setting(conn, "session_secret")
        if not secret:
            return False
        parts = token.split(".")
        if len(parts) != 3:
            return False
        issued_text, nonce, signature = parts
        if not nonce:
            return False
        try:
            issued_at = int(issued_text)
        except ValueError:
            return False
        if issued_at > int(time.time()) or int(time.time()) - issued_at > AUTH_SESSION_TTL_SECONDS:
            return False
        payload = f"{issued_text}.{nonce}".encode("utf-8")
        expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)

    @staticmethod
    def _is_public_path(path: str) -> bool:
        return (
            path == "/"
            or path == "/healthz"
            or path == "/api/health"
            or path in {"/api/auth/status", "/api/auth/login", "/api/auth/logout"}
            or path.startswith("/assets/")
            or path.startswith("/iclock/")
        )

    def _send_auth_cookie(self, token: str, max_age: int = AUTH_SESSION_TTL_SECONDS) -> str:
        return (
            f"{AUTH_COOKIE_NAME}={token}; Path=/; Max-Age={max_age}; "
            "HttpOnly; SameSite=Lax"
        )

    def _handle_auth_write(self, path: str, raw_body: bytes) -> bool:
        if path not in {"/api/auth/login", "/api/auth/logout", "/api/auth/password"}:
            return False
        if path == "/api/auth/logout":
            self._send_json(
                200,
                {"authenticated": False},
                {"Set-Cookie": self._send_auth_cookie("", 0)},
            )
            return True
        try:
            payload = self._json_body(raw_body)
        except ValueError as error:
            self._send_json(400, {"error": str(error)})
            return True
        if not isinstance(payload, dict):
            self._send_json(400, {"error": "Body must be a JSON object"})
            return True
        password = str(payload.get("password", ""))
        if path == "/api/auth/login":
            with connect_db() as conn:
                encoded = operator_setting(conn, "password_hash") or ""
                secret = operator_setting(conn, "session_secret") or ""
            if not verify_operator_password(password, encoded) or not secret:
                self._send_json(401, {"error": "رمز عبور نادرست است."})
                return True
            issued_at = str(int(time.time()))
            nonce = secrets.token_urlsafe(24)
            payload_text = f"{issued_at}.{nonce}"
            signature = hmac.new(
                secret.encode("utf-8"),
                payload_text.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            token = f"{payload_text}.{signature}"
            self._send_json(
                200,
                {"authenticated": True},
                {"Set-Cookie": self._send_auth_cookie(token)},
            )
            return True
        if not self._is_authenticated():
            self._send_json(401, {"error": "نیاز به ورود دارید."})
            return True
        if len(password) < 8:
            self._send_json(400, {"error": "رمز عبور باید حداقل ۸ نویسه باشد."})
            return True
        with connect_db() as conn:
            set_operator_setting(conn, "password_hash", hash_operator_password(password))
            set_operator_setting(conn, "session_secret", secrets.token_hex(32))
            conn.commit()
            secret = operator_setting(conn, "session_secret") or ""
        issued_at = str(int(time.time()))
        nonce = secrets.token_urlsafe(24)
        payload_text = f"{issued_at}.{nonce}"
        signature = hmac.new(
            secret.encode("utf-8"),
            payload_text.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        token = f"{payload_text}.{signature}"
        self._send_json(
            200,
            {"authenticated": True},
            {"Set-Cookie": self._send_auth_cookie(token)},
        )
        return True

    def _parse(self) -> tuple[str, dict]:
        parsed = urlparse(self.path)
        query = {
            key: value[0] if len(value) == 1 else value
            for key, value in parse_qs(parsed.query).items()
        }
        return parsed.path, normalize_query(query)

    def _read_body_bytes(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0") or "0")
        return self.rfile.read(length) if length > 0 else b""

    def _send_bytes(
        self,
        status: int,
        payload: bytes,
        content_type: str,
        headers: dict | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)

    def _send_text(self, status: int, content: str) -> None:
        self._send_bytes(status, content.encode("utf-8"), "text/plain; charset=utf-8")

    def _send_json(self, status: int, data: dict | list, headers: dict | None = None) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._send_bytes(status, payload, "application/json; charset=utf-8", headers)

    def _queue_command(self, conn: sqlite3.Connection, sn: str, command_text: str) -> int:
        return insert_queued_command(conn, sn, command_text)

    def _queue_many(self, conn: sqlite3.Connection, sn: str, commands: list[str]) -> list[dict]:
        return [
            {"id": self._queue_command(conn, sn, command), "command": command}
            for command in commands
            if command.strip()
        ]

    def _json_body(self, raw_body: bytes) -> dict | list:
        if not raw_body:
            return {}
        try:
            return json.loads(raw_body.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            raise ValueError("Body must be valid JSON") from exc

    def _payload_sn(self, payload: dict | list, query: dict) -> str:
        if isinstance(payload, dict):
            value = payload.get("sn", payload.get("SN", ""))
        else:
            value = ""
        return str(value or query.get("sn", "")).strip()

    def _drain_command_for_device(self, conn: sqlite3.Connection, sn: str) -> str | None:
        row = conn.execute(
            """
            SELECT id, command_text FROM command_queue
            WHERE sn = ? AND status = 'queued'
            ORDER BY id ASC LIMIT 1
            """,
            (sn,),
        ).fetchone()
        if not row:
            return None
        command_id = row["id"]
        command_text = row["command_text"].strip()
        if command_text.startswith("C:"):
            parts = command_text.split(":", 2)
            command_text = parts[2].strip() if len(parts) == 3 else command_text
        wire_text = f"C:{command_id}:{command_text}"
        conn.execute(
            """
            UPDATE command_queue
            SET status='sent', ts_sent=?, wire_id=?, raw_response=?
            WHERE id=?
            """,
            (utc_now(), command_id, wire_text, command_id),
        )
        return wire_text

    def _serve_static(self, path: str) -> bool:
        if path == "/":
            file_path = STATIC_DIR / "index.html"
        elif path.startswith("/assets/"):
            relative_path = path.removeprefix("/assets/")
            root_asset = (STATIC_DIR / relative_path).resolve()
            nested_asset = (STATIC_DIR / "assets" / relative_path).resolve()
            file_path = root_asset if root_asset.is_file() else nested_asset
        else:
            return False
        try:
            file_path = file_path.resolve()
            if STATIC_DIR.resolve() not in file_path.parents:
                self._send_text(403, "Forbidden")
                return True
            payload = file_path.read_bytes()
        except FileNotFoundError:
            self._send_text(404, "Not Found")
            return True
        content_type = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".svg": "image/svg+xml",
            ".woff2": "font/woff2",
        }.get(file_path.suffix, "application/octet-stream")
        self._send_bytes(200, payload, content_type)
        return True

    def _api_get(self, path: str, query: dict) -> bool:
        if path == "/api/auth/status":
            self._send_json(200, {"authenticated": self._is_authenticated()})
            return True

        if path in {"/api/operator-guide", "/api/capabilities", "/api/workflows"}:
            self._send_json(200, operator_guide())
            return True

        if path == "/api/known-commands":
            self._send_json(
                200,
                {
                    "data": [
                        {
                            "id": "users",
                            "label": "دریافت کارکنان",
                            "command": "DATA QUERY USERINFO",
                            "description": "اطلاعات پایه کارکنان را از دستگاه می‌گیرد.",
                            "kind": "read",
                        },
                        {
                            "id": "attendance",
                            "label": "دریافت سوابق حضور",
                            "command": ATTENDANCE_QUERY_COMMAND,
                            "description": "سوابق حضور را از بازه کامل ذخیره‌شده در دستگاه درخواست می‌کند.",
                            "kind": "read",
                        },
                        {
                            "id": "fingerprints",
                            "label": "دریافت اثرانگشت‌ها",
                            "command": "DATA QUERY tablename=templatev10,fielddesc=*,filter=*",
                            "description": "قالب‌های اثرانگشت را درخواست می‌کند.",
                            "kind": "read",
                        },
                        {
                            "id": "faces",
                            "label": "دریافت چهره‌ها",
                            "command": "DATA QUERY tablename=facev7,fielddesc=*,filter=*",
                            "description": "قالب‌های چهره را درخواست می‌کند.",
                            "kind": "read",
                        },
                    ],
                },
            )
            return True

        if path == "/api/backups/export":
            with connect_db() as conn:
                payload = create_backup_zip(conn)
            filename = f"adms-backup-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.zip"
            self._send_bytes(
                200,
                payload,
                "application/zip",
                {"Content-Disposition": f'attachment; filename="{filename}"'},
            )
            return True

        if path == "/api/user-fields":
            self._send_json(200, {"data": user_field_guide()})
            return True

        if path == "/api/health":
            with connect_db() as conn:
                device_count = conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
                user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            self._send_json(200, {"ok": True, "ts": utc_now(), "devices": device_count, "users": user_count})
            return True

        if path == "/api/summary":
            with connect_db() as conn:
                counts = {
                    "devices": conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0],
                    "users": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
                    "biometrics": conn.execute("SELECT COUNT(*) FROM biometrics").fetchone()[0],
                    "fingerprints": conn.execute(
                        "SELECT COUNT(*) FROM biometrics WHERE kind='fingerprint'"
                    ).fetchone()[0],
                    "faces": conn.execute(
                        "SELECT COUNT(*) FROM biometrics WHERE kind='face'"
                    ).fetchone()[0],
                    "attendance": conn.execute("SELECT COUNT(*) FROM attendance_raw").fetchone()[0],
                    "commands": conn.execute("SELECT COUNT(*) FROM command_queue").fetchone()[0],
                    "pending_commands": conn.execute(
                        "SELECT COUNT(*) FROM command_queue WHERE status='queued'"
                    ).fetchone()[0],
                }
                last_ingest = conn.execute(
                    "SELECT ts FROM request_log WHERE path LIKE '/iclock/%' ORDER BY id DESC LIMIT 1"
                ).fetchone()
            counts["last_ingest"] = last_ingest["ts"] if last_ingest else None
            self._send_json(200, counts)
            return True

        if path == "/api/devices":
            with connect_db() as conn:
                rows = conn.execute(
                    """
                    SELECT d.*,
                        (SELECT COUNT(*) FROM users u WHERE u.sn=d.sn) AS user_count,
                        (SELECT COUNT(*) FROM biometrics b WHERE b.sn=d.sn) AS biometric_count,
                        (SELECT COUNT(*) FROM biometrics b
                         WHERE b.sn=d.sn AND b.kind='fingerprint') AS fingerprint_count,
                        (SELECT COUNT(*) FROM biometrics b
                         WHERE b.sn=d.sn AND b.kind='face') AS face_count,
                        (SELECT COUNT(*) FROM attendance_raw a WHERE a.sn=d.sn) AS attendance_count,
                        (SELECT COUNT(*) FROM command_queue c WHERE c.sn=d.sn AND c.status='queued') AS queued_count
                    FROM devices d ORDER BY d.last_seen DESC
                    """
                ).fetchall()
            data = []
            for row in rows:
                item = dict(row)
                item["status"] = effective_device_status(row)
                data.append(item)
            self._send_json(200, {"count": len(data), "data": data})
            return True

        if path == "/api/device-labels":
            with connect_db() as conn:
                rows = conn.execute(
                    "SELECT sn, display_name FROM devices ORDER BY sn"
                ).fetchall()
            self._send_json(200, {"count": len(rows), "data": {row["sn"]: row["display_name"] for row in rows}})
            return True

        if path.startswith("/api/devices/"):
            suffix = unquote(path.split("/api/devices/", 1)[1]).strip("/")
            if suffix and "/" not in suffix:
                sn = clean_device_sn(suffix)
                with connect_db() as conn:
                    row = conn.execute(
                        """
                        SELECT d.*,
                            (SELECT COUNT(*) FROM users u WHERE u.sn=d.sn) AS user_count,
                            (SELECT COUNT(*) FROM biometrics b WHERE b.sn=d.sn) AS biometric_count,
                            (SELECT COUNT(*) FROM biometrics b
                             WHERE b.sn=d.sn AND b.kind='fingerprint') AS fingerprint_count,
                            (SELECT COUNT(*) FROM biometrics b
                             WHERE b.sn=d.sn AND b.kind='face') AS face_count,
                            (SELECT COUNT(*) FROM attendance_raw a WHERE a.sn=d.sn) AS attendance_count,
                            (SELECT COUNT(*) FROM command_queue c
                             WHERE c.sn=d.sn AND c.status='queued') AS queued_count
                        FROM devices d WHERE d.sn=?
                        """,
                        (sn,),
                    ).fetchone()
                if not row:
                    self._send_json(
                        404,
                        {
                            "error": "Device not found",
                            "sn": sn,
                            "message": "Wait for this device to contact ADMS, or register its exact serial number first.",
                        },
                    )
                else:
                    data = dict(row)
                    data["status"] = effective_device_status(row)
                    self._send_json(200, data)
                return True

        if path == "/api/users/export":
            sns = requested_device_sns(query, "sns", "sn")
            output_format = str(query.get("format", "csv")).lower()
            with connect_db() as conn:
                if sns:
                    placeholders = ",".join("?" for _ in sns)
                    rows = conn.execute(
                        f"SELECT * FROM users WHERE sn IN ({placeholders}) ORDER BY sn, pin", sns
                    ).fetchall()
                else:
                    rows = conn.execute("SELECT * FROM users ORDER BY sn, pin").fetchall()
            data = [dict(row) for row in rows]
            if output_format == "json":
                self._send_bytes(
                    200,
                    json.dumps({"count": len(data), "data": data}, ensure_ascii=False, indent=2).encode(),
                    "application/json; charset=utf-8",
                    {"Content-Disposition": "attachment; filename=users.json"},
                )
            else:
                fields = ["sn", "pin", "name", "privilege", "password", "card", "group_id", "tz", "verify"]
                output = io.StringIO()
                writer = csv.DictWriter(output, fieldnames=fields)
                writer.writeheader()
                writer.writerows({field: row.get(field, "") for field in fields} for row in data)
                self._send_bytes(
                    200,
                    output.getvalue().encode("utf-8"),
                    "text/csv; charset=utf-8",
                    {"Content-Disposition": "attachment; filename=users.csv"},
                )
            return True

        if path == "/api/users":
            sns = requested_device_sns(query, "sns", "sn")
            search = str(query.get("search", "")).strip().lower()
            limit = max(1, min(int(str(query.get("limit", "100"))), 1000))
            offset = max(0, int(str(query.get("offset", "0"))))
            where = []
            args: list[str] = []
            if sns:
                placeholders = ",".join("?" for _ in sns)
                where.append(f"sn IN ({placeholders})")
                args.extend(sns)
            if search:
                where.append("(LOWER(pin) LIKE ? OR LOWER(name) LIKE ?)")
                args.extend([f"%{search}%", f"%{search}%"])
            clause = f" WHERE {' AND '.join(where)}" if where else ""
            with connect_db() as conn:
                total = conn.execute(f"SELECT COUNT(*) FROM users{clause}", args).fetchone()[0]
                rows = conn.execute(
                    f"SELECT * FROM users{clause} ORDER BY sn, pin LIMIT ? OFFSET ?",
                    [*args, limit, offset],
                ).fetchall()
            self._send_json(
                200,
                {"count": total, "limit": limit, "offset": offset, "data": [dict(row) for row in rows]},
            )
            return True

        if path.startswith("/api/users/"):
            pin = unquote(path.split("/api/users/", 1)[1]).strip("/")
            sn = str(query.get("sn", "")).strip()
            with connect_db() as conn:
                if sn:
                    row = conn.execute(
                        "SELECT * FROM users WHERE sn=? AND pin=?", (sn, pin)
                    ).fetchone()
                else:
                    rows = conn.execute("SELECT * FROM users WHERE pin=? ORDER BY sn", (pin,)).fetchall()
                    if len(rows) > 1:
                        self._send_json(409, {"error": "sn is required when PIN exists on multiple devices"})
                        return True
                    row = rows[0] if rows else None
            if not row:
                self._send_json(404, {"error": "User not found", "pin": pin, "sn": sn or None})
            else:
                self._send_json(200, dict(row))
            return True

        if path == "/api/biometrics/export":
            sns = requested_device_sns(query, "sns", "sn")
            pin = str(query.get("pin", "")).strip()
            conditions = []
            args: list[str] = []
            if sns:
                placeholders = ",".join("?" for _ in sns)
                conditions.append(f"sn IN ({placeholders})")
                args.extend(sns)
            if pin:
                conditions.append("pin=?")
                args.append(pin)
            clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
            with connect_db() as conn:
                rows = conn.execute(
                    f"SELECT ts,sn,pin,kind,template_no,raw_line FROM biometrics{clause} ORDER BY id",
                    args,
                ).fetchall()
            output = io.StringIO()
            fields = ["ts", "sn", "pin", "kind", "template_no", "raw_line"]
            writer = csv.DictWriter(output, fieldnames=fields)
            writer.writeheader()
            writer.writerows(dict(row) for row in rows)
            self._send_bytes(
                200,
                output.getvalue().encode(),
                "text/csv; charset=utf-8",
                {"Content-Disposition": "attachment; filename=biometrics.csv"},
            )
            return True

        if path == "/api/biometrics":
            sns = requested_device_sns(query, "sns", "sn")
            pin = str(query.get("pin", "")).strip()
            kind = str(query.get("kind", "")).strip()
            limit = max(1, min(int(str(query.get("limit", "500"))), 2000))
            conditions = []
            args: list[str] = []
            if sns:
                placeholders = ",".join("?" for _ in sns)
                conditions.append(f"sn IN ({placeholders})")
                args.extend(sns)
            if pin:
                conditions.append("pin=?")
                args.append(pin)
            if kind:
                conditions.append("kind=?")
                args.append(kind)
            clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
            with connect_db() as conn:
                rows = conn.execute(
                    f"SELECT id,ts,sn,pin,kind,template_no,raw_line FROM biometrics{clause} ORDER BY id DESC LIMIT ?",
                    [*args, limit],
                ).fetchall()
            self._send_json(200, {"count": len(rows), "data": [dict(row) for row in rows]})
            return True

        if path == "/api/attendance/export":
            sns = requested_device_sns(query, "sns", "sn")
            start = parse_filter_datetime(
                query.get("start", query.get("from", query.get("date_from", "")))
            )
            end = parse_filter_datetime(
                query.get("end", query.get("to", query.get("date_to", ""))),
                end_of_day=True,
            )
            with connect_db() as conn:
                if sns:
                    placeholders = ",".join("?" for _ in sns)
                    rows = conn.execute(
                        f"SELECT id,ts,sn,table_name,stamp,raw_line FROM attendance_raw "
                        f"WHERE sn IN ({placeholders}) ORDER BY id DESC",
                        sns,
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT id,ts,sn,table_name,stamp,raw_line FROM attendance_raw ORDER BY id DESC"
                    ).fetchall()
            output = io.StringIO()
            writer = csv.DictWriter(
                output,
                fieldnames=[
                    "id",
                    "event_time",
                    "pin",
                    "status",
                    "verify",
                    "work_code",
                    "ts",
                    "sn",
                    "table_name",
                    "stamp",
                    "raw_line",
                ],
            )
            writer.writeheader()
            for row in rows:
                event_time, event_datetime = attendance_event_time(row["raw_line"])
                if start or end:
                    if event_datetime is None:
                        continue
                    if start and event_datetime < start:
                        continue
                    if end and event_datetime > end:
                        continue
                item = dict(row)
                item.update(attendance_record_details(row["raw_line"]))
                writer.writerow(item)
            filename = f"attendance-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.csv"
            self._send_bytes(
                200,
                output.getvalue().encode("utf-8"),
                "text/csv; charset=utf-8",
                {"Content-Disposition": f'attachment; filename="{filename}"'},
            )
            return True

        if path == "/api/attendance":
            sns = requested_device_sns(query, "sns", "sn")
            limit = max(1, min(int(str(query.get("limit", "100"))), 1000))
            start = parse_filter_datetime(
                query.get("start", query.get("from", query.get("date_from", "")))
            )
            end = parse_filter_datetime(
                query.get("end", query.get("to", query.get("date_to", ""))),
                end_of_day=True,
            )
            with connect_db() as conn:
                if sns:
                    placeholders = ",".join("?" for _ in sns)
                    rows = conn.execute(
                        f"SELECT id,ts,sn,table_name,stamp,raw_line FROM attendance_raw "
                        f"WHERE sn IN ({placeholders}) ORDER BY id DESC"
                        + ("" if start or end else " LIMIT ?"),
                        [*sns, limit] if not (start or end) else sns,
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT id,ts,sn,table_name,stamp,raw_line FROM attendance_raw ORDER BY id DESC"
                        + ("" if start or end else " LIMIT ?"),
                        (limit,) if not (start or end) else (),
                    ).fetchall()
            filtered = []
            for row in rows:
                event_time, event_datetime = attendance_event_time(row["raw_line"])
                if start or end:
                    if event_datetime is None:
                        continue
                    if start and event_datetime < start:
                        continue
                    if end and event_datetime > end:
                        continue
                item = dict(row)
                item.update(attendance_record_details(row["raw_line"]))
                filtered.append(item)
            self._send_json(200, {"count": len(filtered), "data": filtered[:limit]})
            return True

        if path == "/api/requests":
            sn = str(query.get("sn", "")).strip()
            limit = max(1, min(int(str(query.get("limit", "100"))), 1000))
            with connect_db() as conn:
                if sn:
                    rows = conn.execute(
                        "SELECT * FROM request_log WHERE sn=? ORDER BY id DESC LIMIT ?",
                        (sn, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM request_log ORDER BY id DESC LIMIT ?", (limit,)
                    ).fetchall()
            self._send_json(200, {"count": len(rows), "data": [dict(row) for row in rows]})
            return True

        if path == "/api/commands":
            sn = str(query.get("sn", "")).strip()
            limit = max(1, min(int(str(query.get("limit", "100"))), 1000))
            ids_value = query.get("ids", "")
            if isinstance(ids_value, list):
                ids_value = ",".join(str(item) for item in ids_value)
            requested_ids = [
                int(item.strip())
                for item in str(ids_value).split(",")
                if item.strip().isdigit()
            ]
            with connect_db() as conn:
                if requested_ids:
                    placeholders = ",".join("?" for _ in requested_ids)
                    if sn:
                        rows = conn.execute(
                            f"SELECT * FROM command_queue WHERE sn=? AND id IN ({placeholders}) ORDER BY id DESC",
                            [sn, *requested_ids],
                        ).fetchall()
                    else:
                        rows = conn.execute(
                            f"SELECT * FROM command_queue WHERE id IN ({placeholders}) ORDER BY id DESC",
                            requested_ids,
                        ).fetchall()
                elif sn:
                    rows = conn.execute(
                        "SELECT * FROM command_queue WHERE sn=? ORDER BY id DESC LIMIT ?",
                        (sn, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM command_queue ORDER BY id DESC LIMIT ?", (limit,)
                    ).fetchall()
            self._send_json(200, {"count": len(rows), "data": [dict(row) for row in rows]})
            return True

        if path == "/api/command-results":
            sn = str(query.get("sn", "")).strip()
            limit = max(1, min(int(str(query.get("limit", "100"))), 1000))
            with connect_db() as conn:
                if sn:
                    rows = conn.execute(
                        "SELECT * FROM command_results WHERE sn=? ORDER BY id DESC LIMIT ?",
                        (sn, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM command_results ORDER BY id DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
            self._send_json(200, {"count": len(rows), "data": [dict(row) for row in rows]})
            return True

        return False

    def _parse_import_records(self, raw_body: bytes, content_type: str) -> tuple[str, list[dict]]:
        decoded = raw_body.decode("utf-8-sig", errors="replace")
        if "json" in content_type.lower() or decoded.lstrip().startswith(("{", "[")):
            parsed = json.loads(decoded)
            if isinstance(parsed, dict):
                sn = str(parsed.get("sn", parsed.get("SN", ""))).strip()
                records = parsed.get("users", parsed.get("data", []))
            else:
                sn = ""
                records = parsed
            if not isinstance(records, list):
                raise ValueError("JSON import must contain a users/data list")
            return sn, [dict(record) for record in records if isinstance(record, dict)]
        reader = csv.DictReader(io.StringIO(decoded))
        return "", [dict(record) for record in reader]

    def _handle_backup_write(self, path: str, raw_body: bytes) -> bool:
        try:
            snapshot, zip_issues, zip_warnings = read_backup_zip(raw_body)
            with connect_db() as conn:
                known_sns = {
                    str(row["sn"])
                    for row in conn.execute("SELECT sn FROM devices").fetchall()
                    if row["sn"]
                }
            inspection = inspect_backup_snapshot(snapshot, known_sns)
            inspection["issues"] = zip_issues + inspection["issues"]
            inspection["warnings"] = zip_warnings + inspection["warnings"]
            inspection["compatible"] = not any(
                item["severity"] == "error" for item in inspection["issues"]
            )
            if path == "/api/backups/inspect":
                self._send_json(200, inspection)
                return True
            if not inspection["compatible"]:
                self._send_json(
                    422,
                    {
                        "error": "Backup consistency errors must be resolved before restore",
                        **inspection,
                    },
                )
                return True
            try:
                options = json.loads(self.headers.get("X-Backup-Options", "{}") or "{}")
            except json.JSONDecodeError as exc:
                self._send_json(400, {"error": f"Invalid X-Backup-Options JSON: {exc}"})
                return True
            if not isinstance(options, dict):
                self._send_json(400, {"error": "X-Backup-Options must be a JSON object"})
                return True
            with connect_db() as conn:
                result = queue_backup_restore(conn, snapshot, options, known_sns)
                conn.commit()
            result["inspection"] = inspection
            result["mode"] = str(options.get("mode", "matching")).strip().lower()
            result["warning"] = (
                "Attendance/history and old command rows stay in the ZIP; "
                "only employee records and supported fingerprint/face templates are queued to devices."
            )
            self._send_json(200, result)
            return True
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
            return True
        except (OSError, zipfile.BadZipFile) as exc:
            self._send_json(400, {"error": f"Could not read backup ZIP: {exc}"})
            return True

    def _handle_api_write(self, method: str, path: str, raw_body: bytes, query: dict) -> bool:
        if not path.startswith("/api/"):
            return False
        if path in {"/api/backups/inspect", "/api/backups/restore"} and method == "POST":
            return self._handle_backup_write(path, raw_body)
        if path == "/api/users/import" and method == "POST":
            payload = {}
        else:
            try:
                payload = self._json_body(raw_body) if raw_body else {}
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
                return True
        if not isinstance(payload, (dict, list)):
            self._send_json(400, {"error": "JSON body must be an object or list"})
            return True

        if path == "/api/users/import" and method == "POST":
            try:
                import_sn, records = self._parse_import_records(
                    raw_body, self.headers.get("Content-Type", "")
                )
            except (ValueError, json.JSONDecodeError) as exc:
                self._send_json(400, {"error": f"Invalid import: {exc}"})
                return True
            sn = import_sn or str(query.get("sn", "")).strip() or self.headers.get("X-Device-SN", "").strip()
            if not sn:
                self._send_json(400, {"error": "sn is required in JSON, query, or X-Device-SN"})
                return True
            queued = []
            skipped = []
            with connect_db() as conn:
                for index, record in enumerate(records, start=1):
                    record["pin"] = str(record.get("pin", record.get("PIN", ""))).strip()
                    if not record["pin"]:
                        skipped.append({"row": index, "reason": "missing pin"})
                        continue
                    queued.extend(self._queue_many(conn, sn, build_user_commands(record)))
                conn.commit()
            self._send_json(200, {"sn": sn, "queued": queued, "skipped": skipped})
            return True

        if path == "/api/users/copy" and method == "POST":
            if not isinstance(payload, dict):
                self._send_json(400, {"error": "JSON body must be an object"})
                return True
            try:
                source_sn = clean_device_sn(payload.get("source_sn", payload.get("from_sn", "")))
                pin = str(payload.get("pin", "")).strip()
                raw_targets = payload.get("target_sns", payload.get("targets", []))
                resolve_all = False
                if isinstance(raw_targets, str):
                    raw_val = raw_targets.strip().lower()
                    if raw_val in ("*", "all"):
                        resolve_all = True
                        raw_targets = []
                    else:
                        raw_targets = [item.strip() for item in raw_targets.split(",") if item.strip()]
                if not isinstance(raw_targets, list):
                    raise ValueError("target_sns must be a list or comma-separated string")
                target_sns = []
                for raw_target in raw_targets:
                    target = clean_device_sn(raw_target)
                    if target and target not in target_sns:
                        target_sns.append(target)
                if not source_sn:
                    raise ValueError("source_sn is required")
                if not pin:
                    raise ValueError("pin is required")
                if not target_sns and not resolve_all:
                    raise ValueError("target_sns must contain at least one device SN")
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
                return True

            include_biometrics = as_bool(payload.get("include_biometrics"), False)
            dual_mode = as_bool(payload.get("dual_mode"), True)
            with connect_db() as conn:
                if resolve_all:
                    all_rows = conn.execute(
                        "SELECT sn FROM devices WHERE sn != ? ORDER BY sn",
                        (source_sn,),
                    ).fetchall()
                    target_sns = [row["sn"] for row in all_rows]
                    if not target_sns:
                        self._send_json(
                            409, {
                                "error": "No other devices available",
                                "source_sn": source_sn,
                                "pin": pin,
                                "message": "No other known devices. Register more devices first.",
                            },
                        )
                        return True
                source_user = conn.execute(
                    "SELECT * FROM users WHERE sn=? AND pin=?",
                    (source_sn, pin),
                ).fetchone()
                if not source_user:
                    self._send_json(
                        404,
                        {
                            "error": "Source user not found",
                            "source_sn": source_sn,
                            "pin": pin,
                            "message": "Import or query the source device first.",
                        },
                    )
                    return True

                placeholders = ",".join("?" for _ in target_sns)
                known_rows = conn.execute(
                    f"SELECT sn FROM devices WHERE sn IN ({placeholders})",
                    target_sns,
                ).fetchall()
                known_targets = {row["sn"] for row in known_rows}
                rejected_targets = [
                    {
                        "sn": target,
                        "reason": "unknown_device",
                        "message": "The device has not registered with ADMS yet.",
                    }
                    for target in target_sns
                    if target not in known_targets
                ]
                accepted_targets = [
                    target
                    for target in target_sns
                    if target in known_targets and target != source_sn
                ]
                if not accepted_targets:
                    self._send_json(
                        409,
                        {
                            "error": "No valid target devices",
                            "source_sn": source_sn,
                            "pin": pin,
                            "rejected_targets": rejected_targets
                            or [{"sn": source_sn, "reason": "source_device_selected"}],
                        },
                    )
                    return True

                biometric_rows = conn.execute(
                    """
                    SELECT pin,kind,template_no,raw_line
                    FROM biometrics
                    WHERE sn=? AND pin=?
                    ORDER BY id
                    """,
                    (source_sn, pin),
                ).fetchall()
                source_user_data = dict(source_user)
                # Fetch display_name map for enriched response
                label_map = {}
                if accepted_targets:
                    ph = ",".join("?" for _ in accepted_targets)
                    label_rows = conn.execute(
                        f"SELECT sn, display_name FROM devices WHERE sn IN ({ph})",
                        accepted_targets,
                    ).fetchall()
                    label_map = {row["sn"]: row["display_name"] for row in label_rows}
                targets = []
                for target in accepted_targets:
                    queued = self._queue_many(
                        conn,
                        target,
                        build_user_commands(source_user_data, dual_mode),
                    )
                    copied_biometrics = []
                    if include_biometrics:
                        for biometric_row in biometric_rows:
                            parsed = parse_biometric_line(biometric_row["raw_line"])
                            if not parsed or not parsed.get("template"):
                                continue
                            if parsed["kind"] == "file":
                                continue
                            command = biometric_command(
                                {
                                    "pin": pin,
                                    "kind": parsed["kind"],
                                    "template_no": parsed.get("template_no", ""),
                                    "template": parsed["template"],
                                }
                            )
                            copied_biometrics.extend(self._queue_many(conn, target, [command]))
                        queued.extend(copied_biometrics)
                    targets.append(
                        {
                            "sn": target,
                            "display_name": label_map.get(target, ""),
                            "queued": queued,
                            "biometrics_queued": len(copied_biometrics),
                        }
                    )
                conn.commit()
            self._send_json(
                200,
                {
                    "source": {"sn": source_sn, "pin": pin},
                    "targets": targets,
                    "rejected_targets": rejected_targets,
                    "resolve_all": resolve_all,
                    "include_biometrics": include_biometrics,
                    "warning": "Commands are queued per target SN. Verify each target by its ACK and a follow-up query; biometric acceptance depends on firmware.",
                },
            )
            return True

        if path == "/api/users/copy-many" and method == "POST":
            if not isinstance(payload, dict):
                self._send_json(400, {"error": "JSON body must be an object"})
                return True
            try:
                source_sn = clean_device_sn(payload.get("source_sn", payload.get("from_sn", "")))
                pins_raw = payload.get("pins", payload.get("pin_list", []))
                if isinstance(pins_raw, str):
                    pins_raw = [p.strip() for p in pins_raw.split(",") if p.strip()]
                if not isinstance(pins_raw, list):
                    raise ValueError("pins must be a list or comma-separated string")
                pins = [str(p).strip() for p in pins_raw if str(p).strip()]
                raw_targets = payload.get("target_sns", payload.get("targets", []))
                resolve_all = False
                if isinstance(raw_targets, str):
                    raw_val = raw_targets.strip().lower()
                    if raw_val in ("*", "all"):
                        resolve_all = True
                        raw_targets = []
                    else:
                        raw_targets = [item.strip() for item in raw_targets.split(",") if item.strip()]
                if not isinstance(raw_targets, list):
                    raise ValueError("target_sns must be a list or comma-separated string")
                target_sns = []
                for raw_target in raw_targets:
                    target = clean_device_sn(raw_target)
                    if target and target not in target_sns:
                        target_sns.append(target)
                if not source_sn:
                    raise ValueError("source_sn is required")
                if not pins:
                    raise ValueError("pins must contain at least one PIN")
                if not target_sns and not resolve_all:
                    raise ValueError("target_sns must contain at least one device SN")
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
                return True

            include_biometrics = as_bool(payload.get("include_biometrics"), False)
            dual_mode = as_bool(payload.get("dual_mode"), True)
            with connect_db() as conn:
                if resolve_all:
                    all_rows = conn.execute(
                        "SELECT sn FROM devices WHERE sn != ? ORDER BY sn",
                        (source_sn,),
                    ).fetchall()
                    target_sns = [row["sn"] for row in all_rows]
                    if not target_sns:
                        self._send_json(409, {"error": "No other devices available", "source_sn": source_sn})
                        return True
                if not target_sns:
                    self._send_json(400, {"error": "target_sns required"})
                    return True

                placeholders = ",".join("?" for _ in target_sns)
                known_rows = conn.execute(
                    f"SELECT sn FROM devices WHERE sn IN ({placeholders})",
                    target_sns,
                ).fetchall()
                known_targets = {row["sn"] for row in known_rows}
                label_rows = conn.execute(
                    f"SELECT sn, display_name FROM devices WHERE sn IN ({placeholders})",
                    target_sns,
                ).fetchall()
                label_map = {row["sn"]: row["display_name"] for row in label_rows}

                results = []
                for pin in pins:
                    source_user = conn.execute(
                        "SELECT * FROM users WHERE sn=? AND pin=?", (source_sn, pin),
                    ).fetchone()
                    if not source_user:
                        results.append({"pin": pin, "error": "source_user_not_found", "targets": []})
                        continue
                    biometric_rows = conn.execute(
                        "SELECT pin,kind,template_no,raw_line FROM biometrics WHERE sn=? AND pin=? ORDER BY id",
                        (source_sn, pin),
                    ).fetchall()
                    source_user_data = dict(source_user)
                    pin_targets = []
                    for target in target_sns:
                        if target == source_sn:
                            continue
                        if target not in known_targets:
                            pin_targets.append({"sn": target, "display_name": label_map.get(target, ""), "error": "unknown_device"})
                            continue
                        queued = self._queue_many(conn, target, build_user_commands(source_user_data, dual_mode))
                        copied_biometrics = 0
                        if include_biometrics:
                            for b_row in biometric_rows:
                                parsed = parse_biometric_line(b_row["raw_line"])
                                if not parsed or not parsed.get("template") or parsed["kind"] == "file":
                                    continue
                                cmd = biometric_command({
                                    "pin": pin,
                                    "kind": parsed["kind"],
                                    "template_no": parsed.get("template_no", ""),
                                    "template": parsed["template"],
                                })
                                self._queue_many(conn, target, [cmd])
                                copied_biometrics += 1
                        pin_targets.append({
                            "sn": target,
                            "display_name": label_map.get(target, ""),
                            "queued": queued,
                            "biometrics_queued": copied_biometrics,
                        })
                    results.append({"pin": pin, "targets": pin_targets})
                conn.commit()
            self._send_json(200, {
                "source_sn": source_sn,
                "results": results,
                "include_biometrics": include_biometrics,
                "resolve_all": resolve_all,
                "warning": "Commands are queued per target SN. Verify each target by its ACK and a follow-up query.",
            })
            return True

        if path == "/api/users/query" and method == "POST":
            sn = self._payload_sn(payload, query)
            mode = str(payload.get("mode", "both") if isinstance(payload, dict) else "both").lower()
            if not sn:
                self._send_json(400, {"error": "sn is required"})
                return True
            commands = []
            if mode in {"both", "userinfo"}:
                commands.append("DATA QUERY USERINFO")
            if mode in {"both", "table"}:
                commands.append("DATA QUERY tablename=user,fielddesc=*,filter=*")
            with connect_db() as conn:
                queued = self._queue_many(conn, sn, commands)
                conn.commit()
            self._send_json(200, {"sn": sn, "queued": queued})
            return True

        if path == "/api/biometrics/query" and method == "POST":
            sn = self._payload_sn(payload, query)
            mode = str(payload.get("mode", "both") if isinstance(payload, dict) else "both").lower()
            if not sn:
                self._send_json(400, {"error": "sn is required"})
                return True
            commands = []
            if mode in {"both", "fingerprint", "fp"}:
                commands.append("DATA QUERY tablename=templatev10,fielddesc=*,filter=*")
            if mode in {"both", "face"}:
                commands.append("DATA QUERY tablename=facev7,fielddesc=*,filter=*")
            with connect_db() as conn:
                queued = self._queue_many(conn, sn, commands)
                conn.commit()
            self._send_json(200, {"sn": sn, "queued": queued})
            return True

        if path == "/api/commands" and method == "POST":
            if not isinstance(payload, dict):
                self._send_json(400, {"error": "JSON body must be an object"})
                return True
            sn = self._payload_sn(payload, query)
            command = str(payload.get("command", payload.get("cmd", ""))).strip()
            if not sn or not command:
                self._send_json(400, {"error": "sn and command are required"})
                return True
            with connect_db() as conn:
                queued = self._queue_many(conn, sn, [command])
                conn.commit()
            self._send_json(200, {"sn": sn, "queued": queued})
            return True

        if path == "/api/users" and method == "POST":
            if not isinstance(payload, dict):
                self._send_json(400, {"error": "JSON body must be an object"})
                return True
            sn = self._payload_sn(payload, query)
            pin = str(payload.get("pin", "")).strip()
            if not sn or not pin:
                self._send_json(400, {"error": "sn and pin are required"})
                return True
            dual_mode = as_bool(payload.get("dual_mode"), True)
            with connect_db() as conn:
                queued = self._queue_many(conn, sn, build_user_commands(payload, dual_mode))
                conn.commit()
            self._send_json(200, {"sn": sn, "pin": pin, "queued": queued})
            return True

        if path == "/api/biometrics" and method == "POST":
            if not isinstance(payload, dict):
                self._send_json(400, {"error": "JSON body must be an object"})
                return True
            sn = self._payload_sn(payload, query)
            if not sn:
                self._send_json(400, {"error": "sn is required"})
                return True
            try:
                command = biometric_command(payload)
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
                return True
            with connect_db() as conn:
                queued = self._queue_many(conn, sn, [command])
                conn.commit()
            self._send_json(
                200,
                {
                    "sn": sn,
                    "pin": payload.get("pin"),
                    "queued": queued,
                    "warning": "Template write syntax is firmware-dependent; verify with device ACK and re-query.",
                },
            )
            return True

        if path.startswith("/api/devices/") and path.endswith("/sync") and method == "POST":
            sn = unquote(path.split("/api/devices/", 1)[1][:-len("/sync")]).strip("/")
            if not sn:
                self._send_json(400, {"error": "sn is required"})
                return True
            with connect_db() as conn:
                queued = self._queue_many(
                    conn,
                    sn,
                    [
                        "DATA QUERY USERINFO",
                        "DATA QUERY tablename=user,fielddesc=*,filter=*",
                        "DATA QUERY tablename=templatev10,fielddesc=*,filter=*",
                        "DATA QUERY tablename=facev7,fielddesc=*,filter=*",
                        ATTENDANCE_QUERY_COMMAND,
                    ],
                )
                conn.commit()
            self._send_json(200, {"sn": sn, "queued": queued})
            return True

        if path.startswith("/api/devices/") and method == "PUT":
            suffix = unquote(path.split("/api/devices/", 1)[1]).strip("/")
            is_label_route = suffix.endswith("/label")
            sn = suffix[:-len("/label")].strip("/") if is_label_route else suffix
            try:
                sn = clean_device_sn(sn)
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
                return True
            if not isinstance(payload, dict):
                self._send_json(400, {"error": "JSON body must be an object"})
                return True
            display_name = str(
                payload.get(
                    "display_name",
                    payload.get("label", payload.get("name", "")),
                )
            ).strip()
            with connect_db() as conn:
                conn.execute(
                    """
                    INSERT INTO devices(sn, display_name, first_seen, last_seen, status)
                    VALUES (?, ?, ?, ?, 'manual')
                    ON CONFLICT(sn) DO UPDATE SET display_name=excluded.display_name
                    """,
                    (sn, display_name, utc_now(), utc_now()),
                )
                conn.commit()
            self._send_json(
                200,
                {
                    "sn": sn,
                    "display_name": display_name,
                    "message": "Friendly device label saved. Commands still target the exact serial number.",
                },
            )
            return True

        if path.startswith("/api/users/"):
            pin = unquote(path.split("/api/users/", 1)[1]).strip("/")
            if method == "PUT":
                if not isinstance(payload, dict):
                    self._send_json(400, {"error": "JSON body must be an object"})
                    return True
                sn = self._payload_sn(payload, query)
                if not sn:
                    self._send_json(400, {"error": "sn is required"})
                    return True
                payload["pin"] = pin
                with connect_db() as conn:
                    queued = self._queue_many(
                        conn,
                        sn,
                        build_user_commands(payload, as_bool(payload.get("dual_mode"), True)),
                    )
                    conn.commit()
                self._send_json(200, {"sn": sn, "pin": pin, "queued": queued})
                return True
            if method == "DELETE":
                sn = str(query.get("sn", "")).strip()
                if not sn and isinstance(payload, dict):
                    sn = str(payload.get("sn", "")).strip()
                if not sn:
                    self._send_json(400, {"error": "sn is required"})
                    return True
                dual_mode = str(query.get("dual_mode", "1")).lower() not in {"0", "false"}
                commands = [f"DATA DELETE USERINFO PIN={pin}"]
                if dual_mode:
                    commands.append(f"DATA DELETE user Pin={pin}")
                with connect_db() as conn:
                    queued = self._queue_many(conn, sn, commands)
                    conn.commit()
                self._send_json(200, {"sn": sn, "pin": pin, "queued": queued})
                return True
        return False

    def _record_request(self, method: str, path: str, query: dict, body: str, sn: str | None) -> None:
        with connect_db() as conn:
            if path.startswith("/iclock/"):
                touch_device(conn, sn, path, self.client_address[0], query)
            write_request_log(conn, method, path, query, body, sn)
            conn.commit()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,X-Device-SN")
        self.end_headers()

    def do_GET(self):  # noqa: N802
        path, query = self._parse()
        sn = str(query.get("sn", "")).strip() or None
        self._record_request("GET", path, query, "", sn)
        if self._serve_static(path):
            return
        if path.startswith("/api/") and not self._is_public_path(path) and not self._is_authenticated():
            self._send_json(401, {"error": "نیاز به ورود دارید."})
            return
        if self._api_get(path, query):
            return
        with connect_db() as conn:
            if path == "/iclock/registry":
                self._send_text(200, f"RegistryCode={datetime.now().strftime('%m%d%H%M%S')}")
                return
            if path == "/iclock/push":
                self._send_text(
                    200,
                    "ServerVersion=3.0.1\r\nServerName=ADMS\r\nPushVersion=3.0.1\r\n"
                    "ErrorDelay=10\r\nRequestDelay=3\r\nTransInterval=1\r\n"
                    "TransTables=User ATTLOG Transaction Facev7 templatev10\r\n"
                    "TimeZone=0\r\nRealTime=1\r\nTimeoutSec=10",
                )
                return
            if path == "/iclock/ping":
                self._send_text(200, "OK")
                return
            if path == "/iclock/cdata":
                sn_text = sn or "UNKNOWN_SN"
                self._send_text(
                    200,
                    f"GET OPTION FROM: {sn_text}\r\nStamp=9999\r\n"
                    f"OpStamp={int(datetime.now().timestamp())}\r\n"
                    "ErrorDelay=60\r\nDelay=30\r\nResLogDay=18250\r\n"
                    "ResLogDelCount=10000\r\nResLogCount=50000\r\n"
                    "TransTimes=00:00;14:05\r\nTransInterval=1\r\n"
                    "TransFlag=1111000000\r\nRealtime=1\r\nEncrypt=0",
                )
                return
            if path == "/iclock/getrequest":
                if not sn:
                    self._send_text(400, "Missing SN")
                    return
                wire_text = self._drain_command_for_device(conn, sn)
                conn.commit()
                self._send_text(200, wire_text or "OK")
                return
            if path == "/healthz":
                self._send_text(200, "ok")
                return
        self._send_text(404, "Not Found")

    def do_POST(self):  # noqa: N802
        path, query = self._parse()
        raw_body = self._read_body_bytes()
        body = raw_body.decode("utf-8", errors="replace")
        sn = str(query.get("sn", "")).strip() or None
        logged_body = "" if path.startswith("/api/auth/") else (body[:8192] if path == "/iclock/fdata" else body)
        self._record_request("POST", path, query, logged_body, sn)
        if self._handle_auth_write(path, raw_body):
            return
        if path.startswith("/api/") and not self._is_authenticated():
            self._send_json(401, {"error": "نیاز به ورود دارید."})
            return
        if self._handle_api_write("POST", path, raw_body, query):
            return
        with connect_db() as conn:
            if path == "/iclock/cdata":
                table_name = str(query.get("table", ""))
                stamp = str(query.get("stamp", ""))
                lines = [line.strip() for line in body.splitlines() if line.strip()]
                inserted_count = 0
                for line in lines:
                    is_duplicate_attlog = (
                        table_name.upper() == "ATTLOG"
                        and conn.execute(
                            """
                            SELECT 1
                            FROM attendance_raw
                            WHERE sn=? AND table_name=? AND raw_line=?
                            LIMIT 1
                            """,
                            (sn, table_name, line),
                        ).fetchone()
                    )
                    if is_duplicate_attlog:
                        continue
                    conn.execute(
                        """
                        INSERT INTO attendance_raw(ts,sn,table_name,stamp,raw_line)
                        VALUES(?,?,?,?,?)
                        """,
                        (utc_now(), sn, table_name, stamp, line),
                    )
                    inserted_count += 1
                    if sn:
                        store_canonical_line(conn, sn, line)
                wire_text = self._drain_command_for_device(conn, sn) if sn else None
                conn.commit()
                self._send_text(200, wire_text or f"OK: {inserted_count}")
                return
            if path == "/iclock/querydata":
                lines = [line.strip() for line in body.splitlines() if line.strip()]
                for line in lines:
                    conn.execute(
                        "INSERT INTO querydata_raw(ts,sn,raw_line) VALUES(?,?,?)",
                        (utc_now(), sn, line),
                    )
                    if sn:
                        store_canonical_line(conn, sn, line)
                conn.commit()
                self._send_text(200, "OK")
                return
            if path == "/iclock/fdata":
                metadata = {}
                for line in raw_body[:4096].decode("utf-8", errors="replace").splitlines()[:20]:
                    if "=" in line:
                        key, value = line.split("=", 1)
                        metadata[key.strip().lower()] = value.strip()
                pin = metadata.get("pin")
                cmd = metadata.get("cmd")
                size_hint = metadata.get("size")
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                filename = f"{timestamp}_{sn or 'UNKNOWN_SN'}_{(pin or 'payload').replace('/', '_')}.bin"
                output_path = UPLOAD_DIR / filename
                output_path.write_bytes(raw_body)
                conn.execute(
                    """
                    INSERT INTO fdata_files(ts,sn,pin,cmd,size_hint,content_type,file_path)
                    VALUES(?,?,?,?,?,?,?)
                    """,
                    (
                        utc_now(),
                        sn,
                        pin,
                        cmd,
                        int(size_hint) if size_hint and size_hint.isdigit() else None,
                        self.headers.get("Content-Type"),
                        str(output_path),
                    ),
                )
                if sn and pin:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO biometrics(ts,sn,pin,kind,template_no,raw_line)
                        VALUES(?,?,?,?,?,?)
                        """,
                        (utc_now(), sn, pin, "file", "", f"USERPIC file={output_path}"),
                    )
                conn.commit()
                self._send_text(200, "OK")
                return
            if path == "/iclock/devicecmd":
                parsed = parse_fields(body.replace("&", "\n"))
                cmd_id = int(parsed["id"]) if parsed.get("id", "").lstrip("-").isdigit() else None
                return_code = (
                    int(parsed["return"]) if parsed.get("return", "").lstrip("-").isdigit() else None
                )
                conn.execute(
                    """
                    INSERT INTO command_results(ts,sn,cmd_id,return_code,cmd,raw_body)
                    VALUES(?,?,?,?,?,?)
                    """,
                    (utc_now(), sn, cmd_id, return_code, parsed.get("cmd"), body),
                )
                if cmd_id is not None:
                    conn.execute(
                        """
                        UPDATE command_queue SET status=?, raw_response=?
                        WHERE wire_id=? AND sn=? AND status='sent'
                        """,
                        ("acked" if return_code == 0 else "error", body, cmd_id, sn),
                    )
                conn.commit()
                self._send_text(200, "OK")
                return
        self._send_text(404, "Not Found")

    def do_PUT(self):  # noqa: N802
        path, query = self._parse()
        raw_body = self._read_body_bytes()
        body = raw_body.decode("utf-8", errors="replace")
        sn = str(query.get("sn", "")).strip() or None
        self._record_request("PUT", path, query, "" if path.startswith("/api/auth/") else body, sn)
        if path.startswith("/api/") and not self._is_authenticated():
            self._send_json(401, {"error": "نیاز به ورود دارید."})
            return
        if self._handle_api_write("PUT", path, raw_body, query):
            return
        self._send_json(404, {"error": "Not Found"})

    def do_DELETE(self):  # noqa: N802
        path, query = self._parse()
        raw_body = self._read_body_bytes()
        body = raw_body.decode("utf-8", errors="replace")
        sn = str(query.get("sn", "")).strip() or None
        self._record_request("DELETE", path, query, "" if path.startswith("/api/auth/") else body, sn)
        if path.startswith("/api/") and not self._is_authenticated():
            self._send_json(401, {"error": "نیاز به ورود دارید."})
            return
        if self._handle_api_write("DELETE", path, raw_body, query):
            return
        self._send_json(404, {"error": "Not Found"})

    def log_message(self, fmt: str, *args):
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="ZKTeco ADMS web control server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()
    init_db()
    httpd = ThreadingHTTPServer((args.host, args.port), ADMSHandler)
    print(f"Listening on http://{args.host}:{args.port}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
