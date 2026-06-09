#!/usr/bin/env python3
import argparse
import os
import sqlite3
import sys
import time
from typing import Dict, Iterable


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_TARGET = os.path.join(PROJECT_ROOT, "data", "auth.db")
REQUIRED_LEGACY_COLUMNS = {"username", "password_hash", "is_admin", "created_at", "updated_at"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="从旧系统 SQLite users 表迁移账号到新系统 data/auth.db"
    )
    parser.add_argument(
        "--source",
        required=True,
        help="旧系统 SQLite 数据库文件路径（必须传）",
    )
    parser.add_argument(
        "--target",
        default=DEFAULT_TARGET,
        help=f"新系统 auth.db 路径（默认：{DEFAULT_TARGET}）",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="遇到同名用户时更新目标记录；默认跳过",
    )
    return parser.parse_args()


def open_conn(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def now_utc_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def ensure_users_table_columns_local(conn: sqlite3.Connection):
    columns = {str(item["name"]) for item in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "is_disabled" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN is_disabled INTEGER NOT NULL DEFAULT 0")
    if "disabled_at" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN disabled_at TEXT DEFAULT ''")
    if "updated_at" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")
    conn.execute("UPDATE users SET is_disabled = 0 WHERE is_disabled IS NULL")
    conn.execute("UPDATE users SET disabled_at = '' WHERE disabled_at IS NULL")
    conn.execute("UPDATE users SET updated_at = created_at WHERE COALESCE(updated_at, '') = ''")
    conn.execute("UPDATE users SET updated_at = ? WHERE updated_at IS NULL", (now_utc_iso(),))


def ensure_target_schema_local(target_db: str):
    conn = open_conn(target_db)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                is_disabled INTEGER NOT NULL DEFAULT 0,
                disabled_at TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        ensure_users_table_columns_local(conn)
        conn.commit()
    finally:
        conn.close()


def ensure_target_schema(target_db: str):
    os.environ.setdefault("AITOOL_SKIP_AUTH_BOOTSTRAP", "1")
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)
    try:
        import main as app_main  # pylint: disable=import-outside-toplevel

        original_auth_db_file = app_main.AUTH_DB_FILE
        try:
            app_main.AUTH_DB_FILE = target_db
            app_main.init_auth_db()
        finally:
            app_main.AUTH_DB_FILE = original_auth_db_file
    except Exception as exc:
        print(f"[warn] 复用 main.py 初始化失败，改用脚本内置 schema 初始化：{exc}", file=sys.stderr)
        ensure_target_schema_local(target_db)


def load_legacy_rows(source_db: str) -> Iterable[sqlite3.Row]:
    conn = open_conn(source_db)
    try:
        table_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users' LIMIT 1"
        ).fetchone()
        if not table_exists:
            raise RuntimeError("旧库缺少 users 表")

        columns = {str(item["name"]) for item in conn.execute("PRAGMA table_info(users)").fetchall()}
        missing = REQUIRED_LEGACY_COLUMNS - columns
        if missing:
            raise RuntimeError(f"旧库 users 表缺少字段：{', '.join(sorted(missing))}")

        return conn.execute(
            """
            SELECT username, password_hash, is_admin, created_at, updated_at
            FROM users
            ORDER BY id ASC
            """
        ).fetchall()
    finally:
        conn.close()


def migrate_users(rows: Iterable[sqlite3.Row], target_db: str, replace: bool) -> Dict[str, int]:
    imported = 0
    skipped = 0
    updated = 0

    conn = open_conn(target_db)
    try:
        conn.execute("BEGIN")
        for row in rows:
            username = str(row["username"] or "").strip()
            if not username:
                skipped += 1
                continue

            password_hash = str(row["password_hash"] or "").strip()
            is_admin = 1 if bool(int(row["is_admin"] or 0)) else 0
            created_at = str(row["created_at"] or "").strip()
            updated_at = str(row["updated_at"] or created_at).strip()

            existing = conn.execute("SELECT id FROM users WHERE username = ? LIMIT 1", (username,)).fetchone()
            if existing and not replace:
                skipped += 1
                continue

            if existing:
                conn.execute(
                    """
                    UPDATE users
                    SET password_hash = ?,
                        is_admin = ?,
                        is_disabled = 0,
                        disabled_at = '',
                        created_at = ?,
                        updated_at = ?
                    WHERE username = ?
                    """,
                    (password_hash, is_admin, created_at, updated_at, username),
                )
                updated += 1
                continue

            conn.execute(
                """
                INSERT INTO users (username, password_hash, is_admin, is_disabled, disabled_at, created_at, updated_at)
                VALUES (?, ?, ?, 0, '', ?, ?)
                """,
                (username, password_hash, is_admin, created_at, updated_at),
            )
            imported += 1

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {"imported": imported, "skipped": skipped, "updated": updated}


def main():
    args = parse_args()
    source_db = os.path.abspath(os.path.expanduser(str(args.source)))
    target_db = os.path.abspath(os.path.expanduser(str(args.target)))

    if not os.path.exists(source_db):
        raise FileNotFoundError(f"source 数据库不存在：{source_db}")

    os.makedirs(os.path.dirname(target_db), exist_ok=True)
    ensure_target_schema(target_db)
    rows = load_legacy_rows(source_db)
    stats = migrate_users(rows, target_db, bool(args.replace))

    print(f"source: {source_db}")
    print(f"target: {target_db}")
    print(f"replace: {bool(args.replace)}")
    print(f"imported: {stats['imported']}")
    print(f"skipped: {stats['skipped']}")
    print(f"updated: {stats['updated']}")


if __name__ == "__main__":
    main()
