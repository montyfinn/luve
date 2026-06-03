from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("char_length(username) >= 3", name="ck_users_username_min_length"),
        CheckConstraint("fluency_level IN (1, 2, 3)", name="ck_users_fluency_level"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    # Nullable: Google-only accounts have no password. Uniqueness of google_sub is
    # enforced at the DB level by the partial index in migration 0004.
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    google_sub: Mapped[str | None] = mapped_column(Text, nullable=True)
    fluency_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    quota_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60, server_default=text("60"))
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True, server_default=text("true"))
    is_banned: Mapped[bool] = mapped_column(nullable=False, default=False, server_default=text("false"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
