"""Casos de uso del módulo PayPal."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.oauth.domain.authenticated_user import AuthenticatedUser
from src.paypal.domain.repositories.paypal_gateway import PayPalGatewayPort
from src.shared.config import Settings
from src.shared.entitlement_notifier import EntitlementNotifier
from src.shared.errors import (
    DomainError,
    ProviderError,
    SubscriptionNotFoundError,
    WebhookVerificationError,
)
from src.shared.models import Provider, Subscription, SubscriptionStatus
from src.shared.plan_catalog import get_plan
from src.shared.repositories import SubscriptionRepositoryPort

_log = logging.getLogger("paypal.cancel")

# Nombres de error que PayPal devuelve cuando el recurso ya no existe de su
# lado (nunca se aprobó, o quedó huérfano por cualquier motivo). En ese caso
# no hay nada que cancelar EN PayPal — insistir solo deja al usuario con una
# suscripción fantasma que nunca podrá cancelar desde la app.
_PAYPAL_RECURSO_INEXISTENTE = {"RESOURCE_NOT_FOUND", "INVALID_RESOURCE_ID"}


def _es_recurso_inexistente(exc: ProviderError) -> bool:
    return exc.details.get("name") in _PAYPAL_RECURSO_INEXISTENTE

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
        entitlement: EntitlementNotifier | None = None,
    ):
        self._gateway = gateway
        self._subs = subscriptions
        self._settings = settings
        self._entitlement = entitlement or EntitlementNotifier(settings)

    async def _notificar_entitlement(self, subscription: Subscription) -> None:
        await self._entitlement.notificar(
            user_id=subscription.user_id,
            plan_key=subscription.plan_key,
            status=subscription.status.value,
            current_period_end=subscription.current_period_end,
        )

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
        # `subscription_id` debería ser el id INTERNO de Pagos (el campo `id`
        # de SubscriptionOut), pero es fácil confundirlo con
        # `provider_subscription_id` (el id de PayPal, ej. "I-XXXX...") ya
        # que ambos son strings opacos y el cliente los tiene los dos a la
        # mano. Fallback: si no matchea como id interno, prueba como id de
        # PayPal — evita cancelaciones que fallan en silencio por mandar el
        # id equivocado.
        subscription = await self._subs.get_for_user(subscription_id, user.user_id)
        if subscription is None:
            candidate = await self._subs.get_by_provider_id(
                Provider.paypal, subscription_id
            )
            if candidate is not None and candidate.user_id == user.user_id:
                subscription = candidate
        if subscription is None or subscription.provider != Provider.paypal:
            raise SubscriptionNotFoundError("Suscripción de PayPal no encontrada.")
        if subscription.provider_subscription_id:
            try:
                await self._gateway.cancel_subscription(
                    subscription.provider_subscription_id,
                    reason="Cancelada por el usuario.",
                )
            except ProviderError as exc:
                if not _es_recurso_inexistente(exc):
                    raise
                _log.warning(
                    "PayPal no tiene la suscripción %s (id interno %s, "
                    "usuario %s) — probablemente nunca se aprobó. Se "
                    "cancela solo del lado de Pagos.",
                    subscription.provider_subscription_id,
                    subscription.id,
                    user.user_id,
                )
        subscription = await self._subs.update_status(
            subscription, SubscriptionStatus.cancelled, cancelled_at=_now()
        )
        await self._subs.record_event(subscription, "subscription.cancelled", {})
        await self._notificar_entitlement(subscription)
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
            await self._notificar_entitlement(subscription)
        await self._subs.record_event(subscription, event_type, body)
