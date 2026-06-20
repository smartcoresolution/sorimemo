import os
from functools import lru_cache
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


def is_database_configured() -> bool:
    return bool(os.getenv("DATABASE_URL", "").strip())


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    return create_engine(database_url, pool_pre_ping=True)


def fetch_one(query: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if not is_database_configured():
        return None
    with get_engine().begin() as conn:
        row = conn.execute(text(query), params or {}).mappings().first()
        return dict(row) if row else None


def fetch_all(query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if not is_database_configured():
        return []
    with get_engine().begin() as conn:
        rows = conn.execute(text(query), params or {}).mappings().all()
        return [dict(row) for row in rows]


def execute(query: str, params: dict[str, Any] | None = None) -> None:
    if not is_database_configured():
        return
    with get_engine().begin() as conn:
        conn.execute(text(query), params or {})


def execute_many(statements: list[str]) -> None:
    if not is_database_configured():
        return
    with get_engine().begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def insert_returning(query: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    with get_engine().begin() as conn:
        row = conn.execute(text(query), params or {}).mappings().one()
        return dict(row)


def get_consent_by_token(consent_token: str) -> dict[str, Any] | None:
    return fetch_one(
        """
        SELECT c.*, u.user_name, u.age_group
        FROM consents c
        LEFT JOIN users u ON u.id = c.user_id
        WHERE c.consent_token = CAST(:consent_token AS uuid)
          AND c.revoked_at IS NULL
        """,
        {"consent_token": consent_token},
    )


def get_audio_file(file_id: str) -> dict[str, Any] | None:
    return fetch_one(
        """
        SELECT *
        FROM audio_files
        WHERE id = CAST(:file_id AS uuid)
        """,
        {"file_id": file_id},
    )


def get_voice_sample(sample_id: str) -> dict[str, Any] | None:
    return fetch_one(
        """
        SELECT *
        FROM voice_samples
        WHERE id = CAST(:sample_id AS uuid)
        """,
        {"sample_id": sample_id},
    )


def get_analysis_result(analysis_id: str) -> dict[str, Any] | None:
    return fetch_one(
        """
        SELECT *
        FROM analysis_results
        WHERE id = CAST(:analysis_id AS uuid)
        """,
        {"analysis_id": analysis_id},
    )
