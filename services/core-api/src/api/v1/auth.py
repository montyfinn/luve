import logging
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user
from src.core.config import settings
from src.core.db import get_db
from src.core.security import create_access_token
from src.models.user import User
from src.schemas.auth import GoogleExchangeRequest, LoginRequest, Token, UserCreate
from src.schemas.user import UserRead
from src.services import oauth_state_store
from src.services.auth_service import (
    authenticate_user,
    register_user,
    resolve_or_create_google_user,
)
from src.services.google_oauth import (
    GoogleAccountConflictError,
    GoogleEmailUnverifiedError,
    GoogleOAuthClient,
    GoogleOAuthError,
    build_authorize_url,
    generate_nonce,
    generate_state,
)


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

_STATE_COOKIE = "g_oauth_state"
_STATE_COOKIE_PATH = "/api/v1/auth/google"


def _build_redis_client() -> Redis:
    if not settings.redis_url:
        raise RuntimeError("REDIS_URL is not configured")
    return Redis.from_url(settings.redis_url, decode_responses=True)


async def _close_redis(redis: Redis) -> None:
    closer = getattr(redis, "aclose", None) or getattr(redis, "close", None)
    if closer is not None:
        await closer()


def get_google_oauth_client() -> GoogleOAuthClient:
    return GoogleOAuthClient(
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        redirect_uri=settings.google_redirect_uri,
        allowed_hd=settings.google_allowed_hd,
    )


def _control_center_redirect(param: str, value: str) -> RedirectResponse:
    sep = "&" if "?" in settings.control_center_url else "?"
    url = f"{settings.control_center_url}{sep}{urlencode({param: value})}"
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


def _clear_state_cookie(response: RedirectResponse) -> RedirectResponse:
    response.delete_cookie(_STATE_COOKIE, path=_STATE_COOKIE_PATH)
    return response


def _safe_error_code(exc: GoogleOAuthError) -> str:
    if isinstance(exc, GoogleEmailUnverifiedError):
        return "email_unverified"
    return "exchange_failed"


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(user_in: UserCreate, db: AsyncSession = Depends(get_db)) -> UserRead:
    user = await register_user(db=db, user_in=user_in)
    return UserRead.model_validate(user)


@router.post("/login", response_model=Token)
async def login(login_in: LoginRequest, db: AsyncSession = Depends(get_db)) -> Token:
    user = await authenticate_user(db=db, email=str(login_in.email), password=login_in.password)
    if user is False:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    return Token(access_token=access_token, token_type="bearer")


@router.get("/me", response_model=UserRead)
async def read_users_me(current_user: User = Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(current_user)


@router.get("/google/start")
async def google_start() -> RedirectResponse:
    if not settings.google_oauth_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Google login is not available"
        )

    state = generate_state()
    nonce = generate_nonce()

    redis = _build_redis_client()
    try:
        await oauth_state_store.store_tx(redis, state, nonce=nonce)
    finally:
        await _close_redis(redis)

    authorize_url = build_authorize_url(
        client_id=settings.google_client_id,
        redirect_uri=settings.google_redirect_uri,
        state=state,
        nonce=nonce,
    )
    response = RedirectResponse(url=authorize_url, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key=_STATE_COOKIE,
        value=state,
        max_age=oauth_state_store.TX_TTL_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
        path=_STATE_COOKIE_PATH,
    )
    logger.info("auth.google.start")
    return response


@router.get("/google/callback")
async def google_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    g_oauth_state: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    if not settings.google_oauth_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Google login is not available"
        )

    if error:
        logger.info("auth.google.callback_error code=cancelled")
        return _clear_state_cookie(_control_center_redirect("auth_error", "cancelled"))

    if (
        not code
        or not state
        or not g_oauth_state
        or not secrets.compare_digest(state, g_oauth_state)
    ):
        logger.info("auth.google.callback_error code=state_mismatch")
        return _clear_state_cookie(_control_center_redirect("auth_error", "state_mismatch"))

    redis = _build_redis_client()
    try:
        tx = await oauth_state_store.pop_tx(redis, state)
        if tx is None or "nonce" not in tx:
            logger.info("auth.google.callback_error code=state_mismatch")
            return _clear_state_cookie(_control_center_redirect("auth_error", "state_mismatch"))

        try:
            identity = await get_google_oauth_client().authenticate(
                code=code, expected_nonce=tx["nonce"]
            )
        except GoogleOAuthError as exc:
            error_code = _safe_error_code(exc)
            logger.info(
                "auth.google.callback_error code=%s type=%s", error_code, type(exc).__name__
            )
            return _clear_state_cookie(_control_center_redirect("auth_error", error_code))

        try:
            user = await resolve_or_create_google_user(
                db, google_sub=identity.sub, email=identity.email, name=identity.name
            )
        except GoogleAccountConflictError as exc:
            logger.info("auth.google.callback_error code=%s", exc.code)
            return _clear_state_cookie(_control_center_redirect("auth_error", exc.code))

        access_token = create_access_token(
            data={"sub": str(user.id)},
            expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        )
        one_time_code = secrets.token_urlsafe(32)
        await oauth_state_store.store_code(redis, one_time_code, access_token)
    finally:
        await _close_redis(redis)

    response = _clear_state_cookie(
        _control_center_redirect("google_code", one_time_code)
    )
    logger.info("auth.google.callback_ok user_id=%s", user.id)
    return response


@router.post("/google/exchange", response_model=Token)
async def google_exchange(payload: GoogleExchangeRequest) -> Token:
    redis = _build_redis_client()
    try:
        access_token = await oauth_state_store.pop_code(redis, payload.google_code)
    finally:
        await _close_redis(redis)

    if not access_token:
        logger.info("auth.google.exchange_miss")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_or_expired_code"
        )
    return Token(access_token=access_token, token_type="bearer")
