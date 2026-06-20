import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from functools import lru_cache

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from app.config import env_bool, env_int, env_str
from app.database import execute, execute_many, fetch_one, insert_returning, is_database_configured
from app.models.schemas import AgeGroup
from app.services.retention_policy import purge_user_data

router = APIRouter()

PBKDF2_ITERATIONS = 210_000
AUTH_TOKEN_TTL_SECONDS = env_int("SORIMEMO_AUTH_TOKEN_TTL_SECONDS", "86400")
PASSWORD_RESET_TTL_SECONDS = env_int("SORIMEMO_PASSWORD_RESET_TTL_SECONDS", "1800")
PASSWORD_RESET_EXPOSE_TOKEN = env_bool("SORIMEMO_PASSWORD_RESET_EXPOSE_TOKEN", "true")
PASSWORD_POLICY_MESSAGE = "비밀번호는 영문자와 숫자를 포함해 8자 이상 입력해 주세요."
_AUTH_TOKEN_SECRET = env_str("SORIMEMO_AUTH_SECRET_KEY") or base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
password_reset_store: dict[str, dict] = {}


class AuthRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)
    age_group: AgeGroup = AgeGroup.OTHER
    display_name: str | None = Field(default=None, max_length=80)
    signup_purpose: str = Field(default="parent_care")


class LoginRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=3)


class PasswordResetConfirmRequest(BaseModel):
    email: str = Field(min_length=3)
    reset_token: str = Field(min_length=6)
    new_password: str = Field(min_length=1)


class AuthResponse(BaseModel):
    user_id: str
    email: str
    age_group: str
    display_name: str | None = None
    signup_purpose: str | None = None
    message: str
    access_token: str
    token_type: str = "bearer"
    expires_in: int


@lru_cache(maxsize=1)
def ensure_auth_schema() -> None:
    try:
        execute_many([
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS email text",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash text",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name text",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS signup_purpose text NOT NULL DEFAULT 'parent_care'",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS role text NOT NULL DEFAULT 'user'",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'active'",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_changed_at timestamptz",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at timestamptz",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now()",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique ON users (lower(email)) WHERE email IS NOT NULL",
            """
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token_hash text NOT NULL UNIQUE,
                expires_at timestamptz NOT NULL,
                used_at timestamptz,
                created_at timestamptz NOT NULL DEFAULT now()
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user ON password_reset_tokens(user_id)",
        ])
    except SQLAlchemyError:
        # The app DB user may not own the table in remote environments. The dev
        # schema already includes the auth columns, so runtime DDL is optional.
        return


def normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if "@" not in normalized or "." not in normalized.rsplit("@", 1)[-1]:
        raise HTTPException(status_code=422, detail="올바른 이메일을 입력해 주세요.")
    return normalized


def validate_password_policy(password: str) -> None:
    if len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise HTTPException(status_code=422, detail=PASSWORD_POLICY_MESSAGE)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, encoded_salt, encoded_digest = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(encoded_salt.encode("ascii"))
        expected = base64.b64decode(encoded_digest.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def _sign_token(unsigned_token: str) -> str:
    return _b64_encode(hmac.new(
        _AUTH_TOKEN_SECRET.encode("utf-8"),
        unsigned_token.encode("ascii"),
        hashlib.sha256,
    ).digest())


def create_access_token(user_id: str, email: str, role: str = "user") -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + AUTH_TOKEN_TTL_SECONDS,
    }
    unsigned = f"{_b64_encode(json.dumps(header, separators=(',', ':')).encode('utf-8'))}.{_b64_encode(json.dumps(payload, separators=(',', ':')).encode('utf-8'))}"
    return f"{unsigned}.{_sign_token(unsigned)}"


def _store_password_reset_token(user_id: str, email: str, reset_token: str) -> None:
    token_hash = hash_reset_token(reset_token)
    try:
        execute(
            """
            INSERT INTO password_reset_tokens (user_id, token_hash, expires_at)
            VALUES (CAST(:user_id AS uuid), :token_hash, now() + (:ttl_seconds * interval '1 second'))
            """,
            {
                "user_id": user_id,
                "token_hash": token_hash,
                "ttl_seconds": PASSWORD_RESET_TTL_SECONDS,
            },
        )
    except SQLAlchemyError:
        password_reset_store[token_hash] = {
            "user_id": user_id,
            "email": email,
            "expires_at": int(time.time()) + PASSWORD_RESET_TTL_SECONDS,
            "used": False,
        }


def _consume_password_reset_token(email: str, reset_token: str) -> str | None:
    token_hash = hash_reset_token(reset_token)
    try:
        row = fetch_one(
            """
            SELECT prt.id, prt.user_id
            FROM password_reset_tokens prt
            JOIN users u ON u.id = prt.user_id
            WHERE lower(u.email) = lower(:email)
              AND prt.token_hash = :token_hash
              AND prt.used_at IS NULL
              AND prt.expires_at > now()
            ORDER BY prt.created_at DESC
            LIMIT 1
            """,
            {"email": email, "token_hash": token_hash},
        )
        if not row:
            return None
        execute(
            """
            UPDATE password_reset_tokens
            SET used_at = now()
            WHERE id = CAST(:token_id AS uuid)
            """,
            {"token_id": str(row["id"])},
        )
        return str(row["user_id"])
    except SQLAlchemyError:
        stored = password_reset_store.get(token_hash)
        if not stored or stored["used"] or stored["email"] != email or stored["expires_at"] < int(time.time()):
            return None
        stored["used"] = True
        return str(stored["user_id"])


def verify_access_token(token: str) -> dict:
    try:
        header, payload, signature = token.split(".", 2)
        unsigned = f"{header}.{payload}"
        if not hmac.compare_digest(signature, _sign_token(unsigned)):
            raise ValueError("invalid signature")
        decoded = json.loads(_b64_decode(payload))
        if int(decoded.get("exp", 0)) < int(time.time()):
            raise ValueError("expired token")
        user_id = str(decoded.get("sub") or "")
        if not user_id:
            raise ValueError("missing subject")
        return decoded
    except Exception as exc:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.") from exc


def get_current_user(authorization: str | None = Header(default=None, alias="Authorization")) -> dict:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    payload = verify_access_token(token)
    if not is_database_configured():
        raise HTTPException(status_code=503, detail="DB가 설정되어 있지 않습니다.")

    row = fetch_one(
        """
        SELECT id, email, age_group, display_name, signup_purpose, role, status
        FROM users
        WHERE id = CAST(:user_id AS uuid)
        """,
        {"user_id": str(payload["sub"])},
    )
    if not row or row.get("status") != "active":
        raise HTTPException(status_code=401, detail="유효하지 않은 사용자입니다.")
    return {
        "user_id": str(row["id"]),
        "email": row["email"],
        "age_group": row["age_group"],
        "display_name": row.get("display_name"),
        "signup_purpose": row.get("signup_purpose"),
        "role": row["role"],
    }


@router.post("/signup", response_model=AuthResponse)
async def signup(request: AuthRequest):
    if not is_database_configured():
        raise HTTPException(status_code=503, detail="DB가 설정되어 있지 않습니다.")

    ensure_auth_schema()
    email = normalize_email(request.email)
    validate_password_policy(request.password)
    existing = fetch_one(
        """
        SELECT id, email, password_hash, age_group, display_name, signup_purpose, role, status
        FROM users
        WHERE lower(email) = :email
          AND status != 'withdrawn'
        """,
        {"email": email},
    )
    if existing:
        if existing.get("password_hash"):
            raise HTTPException(status_code=409, detail="이미 가입된 이메일입니다. 로그인해 주세요.")
        if existing.get("status") == "locked":
            raise HTTPException(status_code=403, detail="잠긴 계정입니다.")
        execute(
            """
            UPDATE users
            SET password_hash = :password_hash,
                age_group = COALESCE(age_group, :age_group),
                display_name = COALESCE(NULLIF(:display_name, ''), display_name),
                signup_purpose = COALESCE(NULLIF(:signup_purpose, ''), signup_purpose),
                status = 'active',
                password_changed_at = now(),
                updated_at = now()
            WHERE id = CAST(:user_id AS uuid)
            """,
            {
                "user_id": str(existing["id"]),
                "password_hash": hash_password(request.password),
                "age_group": request.age_group.value,
                "display_name": (request.display_name or "").strip(),
                "signup_purpose": request.signup_purpose,
            },
        )
        return AuthResponse(
            user_id=str(existing["id"]),
            email=existing["email"],
            age_group=existing["age_group"] or request.age_group.value,
            display_name=existing.get("display_name") or (request.display_name or "").strip() or None,
            signup_purpose=existing.get("signup_purpose") or request.signup_purpose,
            message="기존 계정의 비밀번호가 설정되었습니다.",
            access_token=create_access_token(str(existing["id"]), existing["email"], existing.get("role") or "user"),
            expires_in=AUTH_TOKEN_TTL_SECONDS,
        )

    row = insert_returning(
        """
        INSERT INTO users (email, password_hash, age_group, display_name, signup_purpose, role, status, password_changed_at, updated_at)
        VALUES (:email, :password_hash, :age_group, NULLIF(:display_name, ''), :signup_purpose, 'user', 'active', now(), now())
        RETURNING id, email, age_group, display_name, signup_purpose
        """,
        {
            "email": email,
            "password_hash": hash_password(request.password),
            "age_group": request.age_group.value,
            "display_name": (request.display_name or "").strip(),
            "signup_purpose": request.signup_purpose,
        },
    )
    return AuthResponse(
        user_id=str(row["id"]),
        email=row["email"],
        age_group=row["age_group"] or AgeGroup.OTHER.value,
        display_name=row.get("display_name"),
        signup_purpose=row.get("signup_purpose"),
        message="테스트 계정이 생성되었습니다.",
        access_token=create_access_token(str(row["id"]), row["email"], "user"),
        expires_in=AUTH_TOKEN_TTL_SECONDS,
    )


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    if not is_database_configured():
        raise HTTPException(status_code=503, detail="DB가 설정되어 있지 않습니다.")

    ensure_auth_schema()
    email = normalize_email(request.email)
    row = fetch_one(
        """
        SELECT id, email, password_hash, age_group, display_name, signup_purpose, role, status
        FROM users
        WHERE lower(email) = :email
        """,
        {"email": email},
    )
    if not row or not row.get("password_hash") or not verify_password(request.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 일치하지 않습니다.")
    if row.get("status") == "withdrawn":
        raise HTTPException(status_code=403, detail="탈퇴 처리된 계정입니다.")
    if row.get("status") == "locked":
        raise HTTPException(status_code=403, detail="잠긴 계정입니다.")

    execute(
        """
        UPDATE users
        SET last_login_at = now(), updated_at = now()
        WHERE id = CAST(:user_id AS uuid)
        """,
        {"user_id": str(row["id"])},
    )
    return AuthResponse(
        user_id=str(row["id"]),
        email=row["email"],
        age_group=row["age_group"] or AgeGroup.OTHER.value,
        display_name=row.get("display_name"),
        signup_purpose=row.get("signup_purpose"),
        message="로그인되었습니다.",
        access_token=create_access_token(str(row["id"]), row["email"], row.get("role") or "user"),
        expires_in=AUTH_TOKEN_TTL_SECONDS,
    )


@router.post("/password-reset/request")
async def request_password_reset(request: PasswordResetRequest):
    if not is_database_configured():
        raise HTTPException(status_code=503, detail="DB가 설정되어 있지 않습니다.")

    ensure_auth_schema()
    email = normalize_email(request.email)
    row = fetch_one(
        """
        SELECT id, email, status
        FROM users
        WHERE lower(email) = :email
          AND status != 'withdrawn'
        """,
        {"email": email},
    )
    response = {
        "message": "가입된 이메일이면 비밀번호 재설정 코드가 발급됩니다.",
        "expires_in": PASSWORD_RESET_TTL_SECONDS,
    }
    if not row:
        return response

    reset_token = secrets.token_urlsafe(24)
    _store_password_reset_token(str(row["id"]), email, reset_token)
    if PASSWORD_RESET_EXPOSE_TOKEN:
        response["reset_token"] = reset_token
    return response


@router.post("/password-reset/confirm")
async def confirm_password_reset(request: PasswordResetConfirmRequest):
    if not is_database_configured():
        raise HTTPException(status_code=503, detail="DB가 설정되어 있지 않습니다.")

    ensure_auth_schema()
    email = normalize_email(request.email)
    validate_password_policy(request.new_password)
    user_id = _consume_password_reset_token(email, request.reset_token.strip())
    if not user_id:
        raise HTTPException(status_code=400, detail="재설정 코드가 올바르지 않거나 만료되었습니다.")

    execute(
        """
        UPDATE users
        SET password_hash = :password_hash,
            status = 'active',
            password_changed_at = now(),
            updated_at = now()
        WHERE id = CAST(:user_id AS uuid)
        """,
        {
            "user_id": user_id,
            "password_hash": hash_password(request.new_password),
        },
    )
    return {"message": "비밀번호가 변경되었습니다. 새 비밀번호로 로그인해 주세요."}


@router.delete("/me/data")
async def delete_my_data(current_user: dict = Depends(get_current_user)):
    return {
        "message": "사용자 데이터 삭제 요청이 처리되었습니다.",
        "deleted": purge_user_data(current_user["user_id"]),
    }
