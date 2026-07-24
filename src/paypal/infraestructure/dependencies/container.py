"""Wiring (inyección de dependencias) del módulo PayPal para FastAPI."""
from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.paypal.application.paypal_service import PayPalService
from src.paypal.infraestructure.adapters.paypal_http_client import PayPalHttpClient
from src.shared.config import Settings, get_settings
from src.shared.database import get_session
from src.shared.entitlement_notifier import EntitlementNotifier
from src.shared.sql_repository import SqlSubscriptionRepository


def get_paypal_service(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> PayPalService:
    return PayPalService(
        gateway=PayPalHttpClient(settings),
        subscriptions=SqlSubscriptionRepository(session),
        settings=settings,
        entitlement=EntitlementNotifier(settings),
    )
