"""Wiring (inyección de dependencias) del módulo Conekta para FastAPI."""
from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.conekta.application.conekta_service import ConektaService
from src.conekta.infraestructure.adapters.conekta_http_client import (
    ConektaHttpClient,
)
from src.shared.config import Settings, get_settings
from src.shared.database import get_session
from src.shared.sql_repository import (
    SqlCustomerRepository,
    SqlSubscriptionRepository,
)


def get_conekta_service(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ConektaService:
    return ConektaService(
        gateway=ConektaHttpClient(settings),
        subscriptions=SqlSubscriptionRepository(session),
        customers=SqlCustomerRepository(session),
        settings=settings,
    )
