"""Endpoints comunes de consulta de suscripciones (historial unificado)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.oauth.domain.authenticated_user import AuthenticatedUser
from src.oauth.infraestructure.dependencies.auth import get_current_user
from src.shared.database import get_session
from src.shared.models import SubscriptionStatus
from src.shared.schemas import SubscriptionOut
from src.shared.sql_repository import SqlSubscriptionRepository

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

_ACTIVE = (SubscriptionStatus.active, SubscriptionStatus.pending)


@router.get("", response_model=list[SubscriptionOut])
async def list_history(
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[SubscriptionOut]:
    """Historial completo de suscripciones del usuario (Conekta + PayPal)."""
    repo = SqlSubscriptionRepository(session)
    subs = await repo.list_for_user(user.user_id)
    return [SubscriptionOut.of(s) for s in subs]


@router.get("/active", response_model=list[SubscriptionOut])
async def list_active(
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[SubscriptionOut]:
    """Suscripción(es) activa(s) o pendientes actuales del usuario."""
    repo = SqlSubscriptionRepository(session)
    subs = await repo.list_for_user(user.user_id)
    return [SubscriptionOut.of(s) for s in subs if s.status in _ACTIVE]
