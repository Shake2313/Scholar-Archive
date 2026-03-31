#!/usr/bin/env python3
"""
Apply the Supabase schema using DATABASE_URL.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

from dotenv import load_dotenv

load_dotenv()


def _parse_database_url(database_url: str) -> dict[str, object]:
    if "://" not in database_url:
        raise ValueError("DATABASE_URL must include a scheme such as postgresql://")

    scheme, rest = database_url.split("://", 1)
    authority, slash, tail = rest.partition("/")
    userinfo, at, hostport = authority.rpartition("@")
    if not at:
        parsed = urlsplit(database_url)
        host = parsed.hostname
        if not host:
            raise ValueError("DATABASE_URL does not contain a valid host.")
        params = {
            "dbname": parsed.path.lstrip("/") or None,
            "host": host,
            "port": parsed.port,
            "user": parsed.username,
            "password": parsed.password,
        }
        params.update({k: v for k, v in parse_qsl(parsed.query)})
        return {k: v for k, v in params.items() if v not in (None, "")}

    user, sep, password = userinfo.partition(":")
    if not sep:
        password = None
    host, colon, port_text = hostport.partition(":")
    if not host:
        raise ValueError("DATABASE_URL does not contain a valid host.")

    query = ""
    dbname = tail
    if "?" in dbname:
        dbname, query = dbname.split("?", 1)

    params: dict[str, object] = {
        "dbname": dbname or None,
        "host": host,
        "port": int(port_text) if colon and port_text else None,
        "user": unquote(user) or None,
        "password": unquote(password) if password is not None else None,
    }
    params.update({k: v for k, v in parse_qsl(query)})

    if scheme.startswith("postgres"):
        params.setdefault("sslmode", "require")
    return {k: v for k, v in params.items() if v not in (None, "")}


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply supabase/schema.sql to DATABASE_URL")
    parser.add_argument(
        "--schema",
        default=str(Path(__file__).with_name("schema.sql")),
        help="Path to the SQL schema file",
    )
    args = parser.parse_args()

    database_url = (
        os.environ.get("DATABASE_POOLER_URL")
        or os.environ.get("SUPABASE_DB_URL")
        or os.environ.get("DATABASE_URL")
    )
    if not database_url:
        raise SystemExit(
            "No database URL is configured. Set DATABASE_POOLER_URL, SUPABASE_DB_URL, or DATABASE_URL."
        )

    schema_path = Path(args.schema)
    if not schema_path.exists():
        raise SystemExit(f"Schema file not found: {schema_path}")

    sql = schema_path.read_text(encoding="utf-8")

    try:
        import psycopg
    except Exception as exc:
        raise SystemExit(
            "psycopg is not installed. Run `python -m pip install -r requirements.txt` first."
        ) from exc

    connect_kwargs = _parse_database_url(database_url)
    with psycopg.connect(autocommit=True, **connect_kwargs) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)

    print(f"Applied schema: {schema_path}")


if __name__ == "__main__":
    main()
