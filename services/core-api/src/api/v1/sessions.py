from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user
from src.core.db import get_db
from src.models.user import User
from src.schemas.session import (
    GradingRead,
    GradingStatusRead,
    SessionCreateRequest,
    SessionListResponse,
    SessionRead,
)
from src.services.session_service import (
    SESSION_LIST_DEFAULT_LIMIT,
    create_webrtc_session,
    get_session_grading,
    get_session_grading_status,
    get_user_session,
    list_user_sessions,
)


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


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    limit: int = Query(SESSION_LIST_DEFAULT_LIMIT, ge=1),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SessionListResponse:
    return await list_user_sessions(
        db,
        current_user=current_user,
        limit=limit,
        offset=offset,
    )


@router.get("/{session_id}/grading/status", response_model=GradingStatusRead)
async def get_grading_status(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GradingStatusRead:
    return await get_session_grading_status(
        db,
        session_id=session_id,
        user_id=current_user.id,
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
