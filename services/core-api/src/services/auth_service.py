import secrets

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import get_password_hash, verify_password
from src.models.user import User
from src.schemas.auth import UserCreate
from src.services.google_oauth import GoogleAccountConflictError


async def register_user(db: AsyncSession, user_in: UserCreate) -> User:
    email = str(user_in.email)
    user = User(
        username=user_in.username,
        email=email,
        password_hash=get_password_hash(user_in.password),
        fluency_level=user_in.fluency_level,
        quota_minutes=user_in.quota_minutes,
    )

    try:
        async with db.begin():
            existing_user = await db.scalar(select(User).where(User.email == email))
            if existing_user is not None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered.",
                )
            db.add(user)
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered.",
        ) from exc

    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User | bool:
    user = await db.scalar(select(User).where(User.email == email))
    if user is None:
        return False
    # Google-only accounts have no password and must never pass password login.
    if user.password_hash is None:
        return False
    if not verify_password(password, user.password_hash):
        return False
    return user


def _derive_username(email: str, name: str | None) -> str:
    """Best-effort display username for a new Google user.

    ``users.username`` is NOT NULL with a >= 3 char check but is NOT unique, so
    collisions are allowed and no disambiguation is required.
    """
    candidate = (name or "").strip() or email.split("@", 1)[0].strip()
    if len(candidate) < 3:
        candidate = f"user_{secrets.token_hex(3)}"
    return candidate[:255]


async def resolve_or_create_google_user(
    db: AsyncSession, *, google_sub: str, email: str, name: str | None
) -> User:
    """Resolve a verified Google identity to a Luve user (no auto-link policy).

    1. Match on ``google_sub`` -> return that user.
    2. Else match on email:
       * none           -> create a new Google-only user (password_hash NULL).
       * password acct  -> raise ``account_exists`` (never silently link).
       * other google   -> raise ``link_conflict``.
    """
    try:
        async with db.begin():
            user = await db.scalar(
                select(User).where(User.google_sub == google_sub, User.deleted_at.is_(None))
            )
            if user is not None:
                return user

            existing = await db.scalar(
                select(User).where(User.email == email, User.deleted_at.is_(None))
            )
            if existing is not None:
                if existing.google_sub and existing.google_sub != google_sub:
                    raise GoogleAccountConflictError("link_conflict")
                # Existing password account (google_sub IS NULL): do NOT auto-link by
                # email — registration never verified the email, so linking would be
                # an account-takeover vector.
                raise GoogleAccountConflictError("account_exists")

            user = User(
                username=_derive_username(email, name),
                email=email,
                password_hash=None,
                google_sub=google_sub,
            )
            db.add(user)
    except IntegrityError:
        # The insert lost a race (a concurrent callback for the same google_sub)
        # or collided with a row invisible to the deleted_at IS NULL lookups
        # (e.g. a soft-deleted account still owning the unique email). Re-query by
        # google_sub: a live winner means a concurrent create succeeded; anything
        # else is an email collision we refuse to link or revive.
        await db.rollback()
        winner = await db.scalar(
            select(User).where(User.google_sub == google_sub, User.deleted_at.is_(None))
        )
        if winner is not None:
            return winner
        raise GoogleAccountConflictError("account_exists") from None

    await db.refresh(user)
    return user
