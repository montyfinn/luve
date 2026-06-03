"""Focused tests for the Google OAuth backend foundation (Commit 1).

No real Google network, no real Redis, no real DB. Google ID tokens are signed
with a throwaway RSA keypair and verified through the real python-jose JWKS path.
Dummy DATABASE_URL/SECRET_KEY/REDIS_URL are set before importing ``src`` so the
settings singleton validates (the same constraint test_main_patch7g6 works around).
"""
from __future__ import annotations

import asyncio
import os
import time
from uuid import uuid4

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://t:t@localhost:5432/t")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-google-oauth-tests")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import pytest  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from jose import jwk, jwt  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

import src.api.v1.auth as auth_module  # noqa: E402
from src.core.config import settings  # noqa: E402
from src.core.db import get_db  # noqa: E402
from src.models.user import User  # noqa: E402
from src.services import oauth_state_store  # noqa: E402
from src.services.auth_service import (  # noqa: E402
    authenticate_user,
    resolve_or_create_google_user,
)
from src.services.google_oauth import (  # noqa: E402
    GoogleAccountConflictError,
    GoogleEmailUnverifiedError,
    GoogleIdentity,
    GoogleIdentityError,
    GoogleOAuthClient,
    build_authorize_url,
)
from src.core.security import get_password_hash  # noqa: E402

CLIENT_ID = "test-client-id.apps.googleusercontent.com"
_KID = "test-kid"

_PRIV = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PRIV_PEM = _PRIV.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
).decode()
_PUB_PEM = (
    _PRIV.public_key()
    .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    .decode()
)


def _jwks() -> dict:
    key = jwk.construct(_PUB_PEM, "RS256").to_dict()
    key.update({"kid": _KID, "use": "sig", "alg": "RS256"})
    return {"keys": [key]}


def _id_token(**overrides) -> str:
    claims = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": "google-sub-123",
        "email": "learner@example.com",
        "email_verified": True,
        "name": "Test Learner",
        "nonce": "the-nonce",
        "iat": int(time.time()),
        "exp": int(time.time()) + 600,
    }
    claims.update(overrides)
    return jwt.encode(claims, _PRIV_PEM, algorithm="RS256", headers={"kid": _KID})


def _client(allowed_hd: str | None = None) -> GoogleOAuthClient:
    return GoogleOAuthClient(
        client_id=CLIENT_ID,
        client_secret="test-secret",
        redirect_uri="https://app.local/api/v1/auth/google/callback",
        allowed_hd=allowed_hd,
    )


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def set(self, key, value, ex=None):  # noqa: ANN001
        self.store[key] = value

    async def getdel(self, key):  # noqa: ANN001
        return self.store.pop(key, None)

    async def aclose(self):
        pass


class _FakeBegin:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *_a):
        return False


class _FakeSession:
    """Returns by_sub for the first scalar() call, by_email for the second."""

    def __init__(self, by_sub=None, by_email=None):  # noqa: ANN001
        self._results = [by_sub, by_email]
        self._i = 0
        self.added: list[User] = []

    def begin(self):
        return _FakeBegin()

    async def scalar(self, *_a, **_k):
        result = self._results[self._i] if self._i < len(self._results) else None
        self._i += 1
        return result

    def add(self, obj):  # noqa: ANN001
        self.added.append(obj)

    async def refresh(self, *_a, **_k):
        pass


class _ScalarSession:
    def __init__(self, user):  # noqa: ANN001
        self._user = user

    async def scalar(self, *_a, **_k):
        return self._user


# ---------------------------------------------------------------------------
# build_authorize_url
# ---------------------------------------------------------------------------

def test_build_authorize_url_has_required_params() -> None:
    url = build_authorize_url(
        client_id=CLIENT_ID, redirect_uri="https://app.local/cb", state="ST", nonce="NO"
    )
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "response_type=code" in url
    assert "scope=openid+email+profile" in url
    assert "state=ST" in url
    assert "nonce=NO" in url


# ---------------------------------------------------------------------------
# verify_id_token (real python-jose JWKS path)
# ---------------------------------------------------------------------------

def test_verify_id_token_success() -> None:
    identity = _client().verify_id_token(_id_token(), _jwks(), expected_nonce="the-nonce")
    assert identity.sub == "google-sub-123"
    assert identity.email == "learner@example.com"
    assert identity.email_verified is True


def test_verify_id_token_unverified_email_raises() -> None:
    with pytest.raises(GoogleEmailUnverifiedError):
        _client().verify_id_token(
            _id_token(email_verified=False), _jwks(), expected_nonce="the-nonce"
        )


def test_verify_id_token_nonce_mismatch_raises() -> None:
    with pytest.raises(GoogleIdentityError):
        _client().verify_id_token(_id_token(), _jwks(), expected_nonce="wrong-nonce")


def test_verify_id_token_bad_audience_raises() -> None:
    with pytest.raises(GoogleIdentityError):
        _client().verify_id_token(
            _id_token(aud="someone-else"), _jwks(), expected_nonce="the-nonce"
        )


def test_verify_id_token_bad_issuer_raises() -> None:
    with pytest.raises(GoogleIdentityError):
        _client().verify_id_token(
            _id_token(iss="https://evil.example.com"), _jwks(), expected_nonce="the-nonce"
        )


def test_verify_id_token_disallowed_hd_raises() -> None:
    with pytest.raises(GoogleIdentityError):
        _client(allowed_hd="mycorp.com").verify_id_token(
            _id_token(hd="other.com"), _jwks(), expected_nonce="the-nonce"
        )


# ---------------------------------------------------------------------------
# oauth_state_store single-use semantics
# ---------------------------------------------------------------------------

def test_state_store_tx_single_use() -> None:
    redis = _FakeRedis()
    asyncio.run(oauth_state_store.store_tx(redis, "state1", nonce="n1"))
    first = asyncio.run(oauth_state_store.pop_tx(redis, "state1"))
    second = asyncio.run(oauth_state_store.pop_tx(redis, "state1"))
    assert first == {"nonce": "n1"}
    assert second is None


def test_state_store_code_single_use() -> None:
    redis = _FakeRedis()
    asyncio.run(oauth_state_store.store_code(redis, "code1", "jwt-token"))
    assert asyncio.run(oauth_state_store.pop_code(redis, "code1")) == "jwt-token"
    assert asyncio.run(oauth_state_store.pop_code(redis, "code1")) is None


# ---------------------------------------------------------------------------
# authenticate_user — Google-only vs password users
# ---------------------------------------------------------------------------

def test_password_login_still_works_for_password_user() -> None:
    user = User(username="pw", email="pw@example.com", password_hash=get_password_hash("secret123"))
    result = asyncio.run(authenticate_user(_ScalarSession(user), email="pw@example.com", password="secret123"))
    assert result is user


def test_password_login_wrong_password_fails() -> None:
    user = User(username="pw", email="pw@example.com", password_hash=get_password_hash("secret123"))
    result = asyncio.run(authenticate_user(_ScalarSession(user), email="pw@example.com", password="nope12345"))
    assert result is False


def test_google_only_user_cannot_password_login() -> None:
    user = User(username="g", email="g@example.com", password_hash=None, google_sub="sub-1")
    result = asyncio.run(authenticate_user(_ScalarSession(user), email="g@example.com", password="anything123"))
    assert result is False


# ---------------------------------------------------------------------------
# resolve_or_create_google_user — no-auto-link policy
# ---------------------------------------------------------------------------

def test_resolve_creates_new_google_user() -> None:
    session = _FakeSession(by_sub=None, by_email=None)
    user = asyncio.run(
        resolve_or_create_google_user(session, google_sub="sub-new", email="new@example.com", name="New")
    )
    assert user.google_sub == "sub-new"
    assert user.password_hash is None
    assert user.email == "new@example.com"
    assert session.added and session.added[0] is user


def test_resolve_returns_existing_google_user() -> None:
    existing = User(username="g", email="g@example.com", password_hash=None, google_sub="sub-x")
    session = _FakeSession(by_sub=existing)
    user = asyncio.run(
        resolve_or_create_google_user(session, google_sub="sub-x", email="g@example.com", name=None)
    )
    assert user is existing
    assert session.added == []


def test_resolve_existing_password_email_rejects_account_exists() -> None:
    pw_user = User(username="pw", email="dup@example.com", password_hash="hash", google_sub=None)
    session = _FakeSession(by_sub=None, by_email=pw_user)
    with pytest.raises(GoogleAccountConflictError) as exc:
        asyncio.run(
            resolve_or_create_google_user(session, google_sub="sub-new", email="dup@example.com", name=None)
        )
    assert exc.value.code == "account_exists"
    assert session.added == []


def test_resolve_email_with_other_google_sub_rejects_link_conflict() -> None:
    other = User(username="o", email="dup@example.com", password_hash=None, google_sub="sub-other")
    session = _FakeSession(by_sub=None, by_email=other)
    with pytest.raises(GoogleAccountConflictError) as exc:
        asyncio.run(
            resolve_or_create_google_user(session, google_sub="sub-new", email="dup@example.com", name=None)
        )
    assert exc.value.code == "link_conflict"


# ---------------------------------------------------------------------------
# Endpoint tests (throwaway app + real router)
# ---------------------------------------------------------------------------

def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(auth_module.router, prefix="/api/v1")

    async def _override_db():
        yield None

    app.dependency_overrides[get_db] = _override_db
    return app


def _enable_google(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "google_client_id", CLIENT_ID)
    monkeypatch.setattr(settings, "google_client_secret", "test-secret")
    monkeypatch.setattr(settings, "google_redirect_uri", "https://app.local/api/v1/auth/google/callback")
    monkeypatch.setattr(settings, "control_center_url", "http://localhost:8000/control-center")


def test_start_feature_off_returns_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "google_client_id", None)
    client = TestClient(_make_app())
    assert client.get("/api/v1/auth/google/start", follow_redirects=False).status_code == 404


def test_start_redirects_to_google_and_sets_cookie(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_google(monkeypatch)
    fake_redis = _FakeRedis()
    monkeypatch.setattr(auth_module, "_build_redis_client", lambda: fake_redis)

    resp = TestClient(_make_app()).get("/api/v1/auth/google/start", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"].startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "g_oauth_state=" in resp.headers.get("set-cookie", "")
    # tx persisted exactly once
    assert len([k for k in fake_redis.store if k.startswith("oauth:google:tx:")]) == 1


def test_callback_state_mismatch_redirects_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_google(monkeypatch)
    client = TestClient(_make_app())
    client.cookies.set("g_oauth_state", "DIFFERENT")
    resp = client.get(
        "/api/v1/auth/google/callback",
        params={"code": "abc", "state": "S1"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "auth_error=state_mismatch" in resp.headers["location"]


def test_callback_unverified_email_redirects_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_google(monkeypatch)
    fake_redis = _FakeRedis()
    asyncio.run(oauth_state_store.store_tx(fake_redis, "S2", nonce="N2"))
    monkeypatch.setattr(auth_module, "_build_redis_client", lambda: fake_redis)

    class _Raiser:
        async def authenticate(self, *, code, expected_nonce):  # noqa: ANN001
            raise GoogleEmailUnverifiedError("nope")

    monkeypatch.setattr(auth_module, "get_google_oauth_client", lambda: _Raiser())
    client = TestClient(_make_app())
    client.cookies.set("g_oauth_state", "S2")
    resp = client.get(
        "/api/v1/auth/google/callback",
        params={"code": "abc", "state": "S2"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "auth_error=email_unverified" in resp.headers["location"]


def test_callback_account_exists_redirects_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_google(monkeypatch)
    fake_redis = _FakeRedis()
    asyncio.run(oauth_state_store.store_tx(fake_redis, "S3", nonce="N3"))
    monkeypatch.setattr(auth_module, "_build_redis_client", lambda: fake_redis)

    class _OkClient:
        async def authenticate(self, *, code, expected_nonce):  # noqa: ANN001
            return GoogleIdentity(sub="s", email="dup@example.com", email_verified=True, name=None, hd=None)

    async def _reject(db, *, google_sub, email, name):  # noqa: ANN001
        raise GoogleAccountConflictError("account_exists")

    monkeypatch.setattr(auth_module, "get_google_oauth_client", lambda: _OkClient())
    monkeypatch.setattr(auth_module, "resolve_or_create_google_user", _reject)
    client = TestClient(_make_app())
    client.cookies.set("g_oauth_state", "S3")
    resp = client.get(
        "/api/v1/auth/google/callback",
        params={"code": "abc", "state": "S3"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "auth_error=account_exists" in resp.headers["location"]


def test_callback_success_then_exchange_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_google(monkeypatch)
    fake_redis = _FakeRedis()
    asyncio.run(oauth_state_store.store_tx(fake_redis, "S4", nonce="N4"))
    monkeypatch.setattr(auth_module, "_build_redis_client", lambda: fake_redis)

    user = User(username="g", email="g@example.com", password_hash=None, google_sub="sub-ok")
    user.id = uuid4()

    class _OkClient:
        async def authenticate(self, *, code, expected_nonce):  # noqa: ANN001
            return GoogleIdentity(sub="sub-ok", email="g@example.com", email_verified=True, name="G", hd=None)

    async def _resolve(db, *, google_sub, email, name):  # noqa: ANN001
        return user

    monkeypatch.setattr(auth_module, "get_google_oauth_client", lambda: _OkClient())
    monkeypatch.setattr(auth_module, "resolve_or_create_google_user", _resolve)

    client = TestClient(_make_app())
    client.cookies.set("g_oauth_state", "S4")
    cb = client.get(
        "/api/v1/auth/google/callback",
        params={"code": "abc", "state": "S4"},
        follow_redirects=False,
    )
    assert cb.status_code == 302
    location = cb.headers["location"]
    assert "google_code=" in location
    one_time = location.split("google_code=", 1)[1].split("&", 1)[0]

    # one-time code resolves to a valid Luve JWT for this user
    ex = client.post("/api/v1/auth/google/exchange", json={"google_code": one_time})
    assert ex.status_code == 200
    token = ex.json()["access_token"]
    claims = jwt.decode(token, os.environ["SECRET_KEY"], algorithms=["HS256"])
    assert claims["sub"] == str(user.id)

    # replay fails (single use)
    replay = client.post("/api/v1/auth/google/exchange", json={"google_code": one_time})
    assert replay.status_code == 400


def test_exchange_unknown_code_returns_400(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_google(monkeypatch)
    monkeypatch.setattr(auth_module, "_build_redis_client", lambda: _FakeRedis())
    resp = TestClient(_make_app()).post(
        "/api/v1/auth/google/exchange", json={"google_code": "does-not-exist"}
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "invalid_or_expired_code"
