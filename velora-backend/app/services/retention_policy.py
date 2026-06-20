from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from app.config import env_bool, env_int
from app.database import execute, execute_many, fetch_all


RESULT_RETENTION_DAYS = env_int("SORIMEMO_RESULT_RETENTION_DAYS", "90")
AUDIO_RETENTION_DAYS = env_int("SORIMEMO_AUDIO_RETENTION_DAYS", "1")
VOICE_SAMPLE_RETENTION_DAYS = env_int("SORIMEMO_VOICE_SAMPLE_RETENTION_DAYS", "1")
DELETE_VOICE_SAMPLE_AFTER_ANALYSIS = env_bool("SORIMEMO_DELETE_VOICE_SAMPLE_AFTER_ANALYSIS", "true")
_RETENTION_SCHEMA_READY = False


def ensure_retention_schema() -> None:
    global _RETENTION_SCHEMA_READY
    if _RETENTION_SCHEMA_READY:
        return
    try:
        execute_many([
            "ALTER TABLE audio_files ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'uploaded'",
            "ALTER TABLE audio_files ADD COLUMN IF NOT EXISTS analyzed_at timestamptz",
            "ALTER TABLE audio_files ADD COLUMN IF NOT EXISTS deleted_at timestamptz",
            "ALTER TABLE audio_files ADD COLUMN IF NOT EXISTS retention_expires_at timestamptz",
            "ALTER TABLE voice_samples ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'active'",
            "ALTER TABLE voice_samples ADD COLUMN IF NOT EXISTS deleted_at timestamptz",
            "ALTER TABLE voice_samples ADD COLUMN IF NOT EXISTS retention_expires_at timestamptz",
            """
            CREATE TABLE IF NOT EXISTS analysis_jobs (
                id uuid PRIMARY KEY,
                user_id uuid REFERENCES users(id) ON DELETE SET NULL,
                audio_file_id uuid REFERENCES audio_files(id) ON DELETE SET NULL,
                voice_sample_id uuid REFERENCES voice_samples(id) ON DELETE SET NULL,
                status text NOT NULL DEFAULT 'queued',
                error_message text,
                started_at timestamptz,
                completed_at timestamptz,
                created_at timestamptz NOT NULL DEFAULT now()
            )
            """,
            "ALTER TABLE analysis_results ADD COLUMN IF NOT EXISTS job_id uuid REFERENCES analysis_jobs(id) ON DELETE SET NULL",
            "ALTER TABLE analysis_results ADD COLUMN IF NOT EXISTS retention_expires_at timestamptz",
            "CREATE INDEX IF NOT EXISTS idx_analysis_jobs_user_created ON analysis_jobs(user_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_analysis_jobs_status ON analysis_jobs(status)",
            "CREATE INDEX IF NOT EXISTS idx_analysis_results_job ON analysis_results(job_id)",
        ])
        _RETENTION_SCHEMA_READY = True
    except SQLAlchemyError:
        return


def remove_file_if_exists(path: str | None) -> bool:
    if not path:
        return False
    target = Path(path)
    try:
        if target.is_file():
            target.unlink()
            return True
    except OSError:
        return False
    return False


def mark_audio_upload_retention(file_id: str, status: str) -> None:
    ensure_retention_schema()
    execute(
        """
        UPDATE audio_files
        SET status = :status,
            retention_expires_at = now() + (:retention_days * interval '1 day')
        WHERE id = CAST(:file_id AS uuid)
        """,
        {
            "file_id": file_id,
            "status": status,
            "retention_days": AUDIO_RETENTION_DAYS,
        },
    )


def mark_voice_sample_retention(sample_id: str) -> None:
    ensure_retention_schema()
    execute(
        """
        UPDATE voice_samples
        SET retention_expires_at = now() + (:retention_days * interval '1 day')
        WHERE id = CAST(:sample_id AS uuid)
        """,
        {
            "sample_id": sample_id,
            "retention_days": VOICE_SAMPLE_RETENTION_DAYS,
        },
    )


def mark_analysis_result_retention(analysis_id: str) -> None:
    ensure_retention_schema()
    execute(
        """
        UPDATE analysis_results
        SET retention_expires_at = now() + (:retention_days * interval '1 day')
        WHERE id = CAST(:analysis_id AS uuid)
        """,
        {
            "analysis_id": analysis_id,
            "retention_days": RESULT_RETENTION_DAYS,
        },
    )


def mark_audio_deleted(file_id: str) -> None:
    ensure_retention_schema()
    execute(
        """
        UPDATE audio_files
        SET raw_deleted_at = COALESCE(raw_deleted_at, now()),
            analyzed_at = COALESCE(analyzed_at, now()),
            deleted_at = COALESCE(deleted_at, now()),
            status = 'raw_deleted',
            storage_path = NULL,
            wav_path = NULL
        WHERE id = CAST(:file_id AS uuid)
        """,
        {"file_id": file_id},
    )


def mark_voice_sample_deleted(sample_id: str) -> None:
    ensure_retention_schema()
    execute(
        """
        UPDATE voice_samples
        SET deleted_at = COALESCE(deleted_at, now()),
            status = 'deleted',
            storage_path = ''
        WHERE id = CAST(:sample_id AS uuid)
        """,
        {"sample_id": sample_id},
    )


def purge_expired_data() -> dict:
    ensure_retention_schema()

    expired_audio = fetch_all(
        """
        SELECT id, storage_path, wav_path
        FROM audio_files
        WHERE retention_expires_at IS NOT NULL
          AND retention_expires_at < now()
          AND deleted_at IS NULL
        """
    )
    audio_files_removed = 0
    for row in expired_audio:
        audio_files_removed += int(remove_file_if_exists(row.get("storage_path")))
        audio_files_removed += int(remove_file_if_exists(row.get("wav_path")))
        mark_audio_deleted(str(row["id"]))

    expired_voice_samples = fetch_all(
        """
        SELECT id, storage_path
        FROM voice_samples
        WHERE retention_expires_at IS NOT NULL
          AND retention_expires_at < now()
          AND deleted_at IS NULL
        """
    )
    voice_files_removed = 0
    for row in expired_voice_samples:
        voice_files_removed += int(remove_file_if_exists(row.get("storage_path")))
        mark_voice_sample_deleted(str(row["id"]))

    expired_results = fetch_all(
        """
        SELECT id
        FROM analysis_results
        WHERE retention_expires_at IS NOT NULL
          AND retention_expires_at < now()
        """
    )
    execute(
        """
        DELETE FROM analysis_results
        WHERE retention_expires_at IS NOT NULL
          AND retention_expires_at < now()
        """
    )

    return {
        "expired_audio_records_marked_deleted": len(expired_audio),
        "expired_audio_files_removed": audio_files_removed,
        "expired_voice_sample_records_marked_deleted": len(expired_voice_samples),
        "expired_voice_sample_files_removed": voice_files_removed,
        "expired_analysis_results_deleted": len(expired_results),
    }


def purge_user_data(user_id: str) -> dict:
    ensure_retention_schema()

    audio_rows = fetch_all(
        """
        SELECT id, storage_path, wav_path
        FROM audio_files
        WHERE user_id = CAST(:user_id AS uuid)
          AND deleted_at IS NULL
        """,
        {"user_id": user_id},
    )
    audio_files_removed = 0
    for row in audio_rows:
        audio_files_removed += int(remove_file_if_exists(row.get("storage_path")))
        audio_files_removed += int(remove_file_if_exists(row.get("wav_path")))
        mark_audio_deleted(str(row["id"]))

    voice_rows = fetch_all(
        """
        SELECT id, storage_path
        FROM voice_samples
        WHERE user_id = CAST(:user_id AS uuid)
          AND deleted_at IS NULL
        """,
        {"user_id": user_id},
    )
    voice_files_removed = 0
    for row in voice_rows:
        voice_files_removed += int(remove_file_if_exists(row.get("storage_path")))
        mark_voice_sample_deleted(str(row["id"]))

    result_rows = fetch_all(
        """
        SELECT ar.id
        FROM analysis_results ar
        JOIN audio_files af ON af.id = ar.audio_file_id
        WHERE af.user_id = CAST(:user_id AS uuid)
        """,
        {"user_id": user_id},
    )
    execute(
        """
        DELETE FROM analysis_results
        WHERE audio_file_id IN (
            SELECT id FROM audio_files WHERE user_id = CAST(:user_id AS uuid)
        )
        """,
        {"user_id": user_id},
    )
    execute(
        """
        UPDATE consents
        SET revoked_at = COALESCE(revoked_at, now())
        WHERE user_id = CAST(:user_id AS uuid)
        """,
        {"user_id": user_id},
    )

    return {
        "audio_records_marked_deleted": len(audio_rows),
        "audio_files_removed": audio_files_removed,
        "voice_sample_records_marked_deleted": len(voice_rows),
        "voice_sample_files_removed": voice_files_removed,
        "analysis_results_deleted": len(result_rows),
        "consents_revoked": True,
    }
