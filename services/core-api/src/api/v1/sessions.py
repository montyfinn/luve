from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user
from src.core.db import get_db
from src.models.user import User
from src.schemas.session import GradingRead, SessionCreateRequest, SessionRead
from src.services.session_service import create_webrtc_session, get_session_grading, get_user_session


router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: SessionCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SessionRead:
    return await create_webrtc_session(
        db,
        current_user=current_user,
        payload=payload,
    )


@router.get("/{session_id}/grading", response_model=GradingRead)
async def get_grading(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GradingRead:
    return await get_session_grading(
        db,
        session_id=session_id,
        user_id=current_user.id,
    )


@router.get("/{session_id}", response_model=SessionRead)
async def get_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SessionRead:
    return await get_user_session(
        db,
        session_id=session_id,
        current_user=current_user,
    )

