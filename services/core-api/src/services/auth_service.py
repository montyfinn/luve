from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import get_password_hash, verify_password
from src.models.user import User
from src.schemas.auth import UserCreate


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
    if not verify_password(password, user.password_hash):
        return False
    return user
