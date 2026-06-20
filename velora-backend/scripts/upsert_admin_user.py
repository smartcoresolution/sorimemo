#!/usr/bin/env python3
"""Create or update a SoriMemo admin user in PostgreSQL."""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
import shutil
import subprocess
import sys


PBKDF2_ITERATIONS = 210_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def build_sql(admin_id: str, password_hash: str, include_schema: bool = True) -> str:
    admin_id_sql = sql_literal(admin_id)
    password_hash_sql = sql_literal(password_hash)
    schema_sql = """
ALTER TABLE users ADD COLUMN IF NOT EXISTS email text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS age_group text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS role text NOT NULL DEFAULT 'user';
ALTER TABLE users ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'active';
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_changed_at timestamptz;
ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique ON users (lower(email)) WHERE email IS NOT NULL;
""" if include_schema else ""

    return f"""
{schema_sql}
WITH updated AS (
    UPDATE users
    SET password_hash = {password_hash_sql},
        role = 'admin',
        status = 'active',
        password_changed_at = now(),
        updated_at = now()
    WHERE lower(email) = lower({admin_id_sql})
    RETURNING id
)
INSERT INTO users (email, password_hash, age_group, role, status, password_changed_at, updated_at)
SELECT {admin_id_sql}, {password_hash_sql}, 'other', 'admin', 'active', now(), now()
WHERE NOT EXISTS (SELECT 1 FROM updated);
"""


def psql_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql+psycopg://"):
        return "postgresql://" + database_url.removeprefix("postgresql+psycopg://")
    if database_url.startswith("postgresql+psycopg2://"):
        return "postgresql://" + database_url.removeprefix("postgresql+psycopg2://")
    return database_url


def run(args: argparse.Namespace) -> int:
    database_url = args.database_url or os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        print("DATABASE_URL is required.", file=sys.stderr)
        return 2
    if not shutil.which("psql"):
        print("psql is required.", file=sys.stderr)
        return 2

    sql = build_sql(args.admin_id.strip(), hash_password(args.password), not args.skip_schema)
    completed = subprocess.run(
        ["psql", psql_database_url(database_url), "-v", "ON_ERROR_STOP=1"],
        input=sql,
        text=True,
        check=False,
    )
    if completed.returncode == 0:
        print(f"admin user is ready: {args.admin_id.strip()}")
    return completed.returncode


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default="")
    parser.add_argument("--admin-id", default="admin")
    parser.add_argument(
        "--password",
        default=os.getenv("SORIMEMO_ADMIN_BOOTSTRAP_PASSWORD", os.getenv("VELORA_ADMIN_BOOTSTRAP_PASSWORD", "")),
    )
    parser.add_argument("--skip-schema", action="store_true", help="Skip ALTER TABLE/CREATE INDEX statements.")
    args = parser.parse_args()

    if not args.admin_id.strip():
        parser.error("--admin-id is required")
    if not args.password:
        parser.error("--password or admin bootstrap password environment variable is required")

    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
