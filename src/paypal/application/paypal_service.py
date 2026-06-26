"""Casos de uso del módulo PayPal."""
from __future__ import annotations

from datetime import datetime, timezone

from src.oauth.domain.authenticated_user import AuthenticatedUser
from src.paypal.domain.repositories.paypal_gateway import PayPalGatewayPort
from src.shared.config import Settings
from src.shared.errors import (
    DomainError,
    SubscriptionNotFoundError,
    WebhookVerificationError,
)
from src.shared.models import Provider, Subscription, SubscriptionStatus
from src.shared.plan_catalog import get_plan
from src.shared.repositories import SubscriptionRepositoryPort

# Estados de PayPal -> estados internos
_STATUS_MAP = {
    "APPROVAL_PENDING": SubscriptionStatus.pending,
    "APPROVED": SubscriptionStatus.pending,
    "ACTIVE": SubscriptionStatus.active,
    "SUSPENDED": SubscriptionStatus.past_due,
    "CANCELLED": SubscriptionStatus.cancelled,
    "EXPIRED": SubscriptionStatus.expired,
}

# Evento de webhook -> estado interno
_EVENT_STATUS = {
    "BILLING.SUBSCRIPTION.ACTIVATED": SubscriptionStatus.active,
    "BILLING.SUBSCRIPTION.RE-ACTIVATED": SubscriptionStatus.active,
    "BILLING.SUBSCRIPTION.UPDATED": SubscriptionStatus.active,
    "BILLING.SUBSCRIPTION.SUSPENDED": SubscriptionStatus.past_due,
    "BILLING.SUBSCRIPTION.PAYMENT.FAILED": SubscriptionStatus.past_due,
    "BILLING.SUBSCRIPTION.CANCELLED": SubscriptionStatus.cancelled,
    "BILLING.SUBSCRIPTION.EXPIRED": SubscriptionStatus.expired,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PayPalSubscriptionResult:
    """DTO de salida para el router (incluye la URL de aprobación)."""

    def __init__(self, subscription: Subscription, approval_url: str | None):
        self.subscription = subscription
        self.approval_url = approval_url


class PayPalService:
    def __init__(
        self,
        gateway: PayPalGatewayPort,
        subscriptions: SubscriptionRepositoryPort,
        settings: Settings,
    ):
        self._gateway = gateway
        self._subs = subscriptions
        self._settings = settings

    async def create_subscription(
        self, user: AuthenticatedUser, plan_key: str
    ) -> PayPalSubscriptionResult:
        plan = get_plan(plan_key, self._settings)
        if not plan.paypal_plan_id:
            raise DomainError(
                f"No hay plan de PayPal configurado para '{plan_key}'. "
                "Corre scripts/bootstrap_paypal.py y llena PAYPAL_PLAN_*."
            )

        existing = await self._subs.get_active_for_user(
            user.user_id, Provider.paypal
        )
        if existing is not None:
            raise DomainError(
                "El usuario ya tiene una suscripción activa/pendiente en PayPal."
            )

        remote = await self._gateway.create_subscription(
            plan_id=plan.paypal_plan_id, user_id=user.user_id, email=user.email
        )
        subscription = Subscription(
            user_id=user.user_id,
            provider=Provider.paypal,
            plan_key=plan_key,
            provider_subscription_id=remote.subscription_id,
            status=_STATUS_MAP.get(remote.status, SubscriptionStatus.pending),
        )
        subscription = await self._subs.add(subscription)
        await self._subs.record_event(
            subscription, "subscription.created", {"status": remote.status}
        )
        return PayPalSubscriptionResult(subscription, remote.approval_url)

    async def cancel(self, user: AuthenticatedUser, subscription_id: str) -> Subscription:
        subscription = await self._subs.get_for_user(subscription_id, user.user_id)
        if subscription is None or subscription.provider != Provider.paypal:
            raise SubscriptionNotFoundError("Suscripción de PayPal no encontrada.")
        if subscription.provider_subscription_id:
            await self._gateway.cancel_subscription(
                subscription.provider_subscription_id,
                reason="Cancelada por el usuario.",
            )
        subscription = await self._subs.update_status(
            subscription, SubscriptionStatus.cancelled, cancelled_at=_now()
        )
        await self._subs.record_event(subscription, "subscription.cancelled", {})
        return subscription

    async def handle_webhook(self, headers: dict, body: dict) -> None:
        if not await self._gateway.verify_webhook(headers, body):
            raise WebhookVerificationError(
                "La firma del webhook de PayPal no pudo verificarse."
            )

        event_type = body.get("event_type", "unknown")
        resource = body.get("resource") or {}
        provider_sub_id = resource.get("id") or resource.get("billing_agreement_id")
        if not provider_sub_id:
            return

        subscription = await self._subs.get_by_provider_id(
            Provider.paypal, provider_sub_id
        )
        if subscription is None:
            return

        new_status = _EVENT_STATUS.get(event_type)
        if new_status is not None:
            cancelled_at = (
                _now()
                if new_status
                in (SubscriptionStatus.cancelled, SubscriptionStatus.expired)
                else None
            )
            subscription = await self._subs.update_status(
                subscription, new_status, cancelled_at=cancelled_at
            )
        await self._subs.record_event(subscription, event_type, body)
