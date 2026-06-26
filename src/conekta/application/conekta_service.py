"""Casos de uso del módulo Conekta (orquestan gateway + persistencia).

Dependen solo de puertos (ConektaGatewayPort, SubscriptionRepositoryPort,
CustomerRepositoryPort), nunca de httpx/SQLAlchemy directamente.
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.conekta.domain.repositories.conekta_gateway import ConektaGatewayPort
from src.oauth.domain.authenticated_user import AuthenticatedUser
from src.shared.config import Settings
from src.shared.errors import (
    DomainError,
    PaymentMethodNotFoundError,
    SubscriptionNotFoundError,
)
from src.shared.models import (
    PaymentCustomer,
    Provider,
    Subscription,
    SubscriptionStatus,
)
from src.shared.plan_catalog import get_plan
from src.shared.repositories import (
    CustomerRepositoryPort,
    SubscriptionRepositoryPort,
)

# Mapea estados de Conekta -> estados internos
_STATUS_MAP = {
    "active": SubscriptionStatus.active,
    "paid": SubscriptionStatus.active,
    "in_trial": SubscriptionStatus.active,
    "past_due": SubscriptionStatus.past_due,
    "payment_failed": SubscriptionStatus.past_due,
    "canceled": SubscriptionStatus.cancelled,
    "cancelled": SubscriptionStatus.cancelled,
}


def _map_status(conekta_status: str) -> SubscriptionStatus:
    return _STATUS_MAP.get(conekta_status, SubscriptionStatus.active)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ConektaService:
    def __init__(
        self,
        gateway: ConektaGatewayPort,
        subscriptions: SubscriptionRepositoryPort,
        customers: CustomerRepositoryPort,
        settings: Settings,
    ):
        self._gateway = gateway
        self._subs = subscriptions
        self._customers = customers
        self._settings = settings

    async def _ensure_customer(
        self, user: AuthenticatedUser, card_token: str
    ) -> PaymentCustomer:
        customer = await self._customers.get(user.user_id, Provider.conekta)
        if customer is None:
            remote = await self._gateway.create_customer(
                name=user.email or user.user_id,
                email=user.email,
                card_token=card_token,
            )
            customer = PaymentCustomer(
                user_id=user.user_id,
                provider=Provider.conekta,
                provider_customer_id=remote.customer_id,
                card_brand=remote.card_brand,
                card_last4=remote.card_last4,
                default_source_id=remote.default_source_id,
            )
            return await self._customers.add(customer)

        # Customer existente: actualiza/asocia la tarjeta nueva si viene un token.
        remote = await self._gateway.add_card(
            customer.provider_customer_id, card_token
        )
        customer.card_brand = remote.card_brand
        customer.card_last4 = remote.card_last4
        customer.default_source_id = remote.default_source_id
        return await self._customers.save(customer)

    async def subscribe(
        self, user: AuthenticatedUser, plan_key: str, card_token: str
    ) -> Subscription:
        plan = get_plan(plan_key, self._settings)
        if not plan.conekta_plan_id:
            raise DomainError(
                f"No hay plan de Conekta configurado para '{plan_key}'."
            )

        existing = await self._subs.get_active_for_user(
            user.user_id, Provider.conekta
        )
        if existing is not None:
            raise DomainError(
                "El usuario ya tiene una suscripción activa en Conekta."
            )

        customer = await self._ensure_customer(user, card_token)
        remote = await self._gateway.create_subscription(
            customer.provider_customer_id, plan.conekta_plan_id
        )

        subscription = Subscription(
            user_id=user.user_id,
            provider=Provider.conekta,
            plan_key=plan_key,
            provider_subscription_id=remote.subscription_id or None,
            status=_map_status(remote.status),
        )
        subscription = await self._subs.add(subscription)
        await self._subs.record_event(
            subscription, "subscription.created", {"status": remote.status}
        )
        return subscription

    async def cancel(self, user: AuthenticatedUser) -> Subscription:
        subscription = await self._subs.get_active_for_user(
            user.user_id, Provider.conekta
        )
        if subscription is None:
            raise SubscriptionNotFoundError(
                "No hay una suscripción activa de Conekta para cancelar."
            )
        customer = await self._customers.get(user.user_id, Provider.conekta)
        if customer is not None:
            await self._gateway.cancel_subscription(customer.provider_customer_id)

        subscription = await self._subs.update_status(
            subscription,
            SubscriptionStatus.cancelled,
            cancelled_at=_now(),
        )
        await self._subs.record_event(subscription, "subscription.cancelled", {})
        return subscription

    async def remove_card(self, user: AuthenticatedUser) -> None:
        customer = await self._customers.get(user.user_id, Provider.conekta)
        if customer is None or not customer.default_source_id:
            raise PaymentMethodNotFoundError(
                "No hay tarjeta asociada para desvincular."
            )
        await self._gateway.delete_source(
            customer.provider_customer_id, customer.default_source_id
        )
        await self._customers.delete_card(customer)

    async def handle_webhook(self, event: dict) -> None:
        """Procesa un evento de webhook de Conekta y actualiza el estado."""
        event_type = event.get("type", "unknown")
        obj = ((event.get("data") or {}).get("object")) or {}
        provider_sub_id = obj.get("id")
        customer_id = obj.get("customer_id")

        subscription: Subscription | None = None
        if provider_sub_id:
            subscription = await self._subs.get_by_provider_id(
                Provider.conekta, provider_sub_id
            )
        if subscription is None and customer_id:
            # Fallback: ubica al usuario por su customer de Conekta.
            # (Conekta vincula 1 suscripción por customer.)
            subscription = await self._find_by_customer(customer_id)

        if subscription is None:
            return  # evento no asociado a una suscripción conocida

        new_status = self._status_from_event(event_type, obj)
        if new_status is not None:
            cancelled_at = (
                _now() if new_status == SubscriptionStatus.cancelled else None
            )
            subscription = await self._subs.update_status(
                subscription, new_status, cancelled_at=cancelled_at
            )
        await self._subs.record_event(subscription, event_type, event)

    async def _find_by_customer(self, customer_id: str) -> Subscription | None:
        # No hay índice directo customer->subscription en el puerto; en la práctica
        # el webhook trae el id de la suscripción. Este fallback queda como no-op
        # seguro si solo llega el customer_id.
        return None

    @staticmethod
    def _status_from_event(
        event_type: str, obj: dict
    ) -> SubscriptionStatus | None:
        if "paid" in event_type:
            return SubscriptionStatus.active
        if "canceled" in event_type or "cancelled" in event_type:
            return SubscriptionStatus.cancelled
        if "payment_failed" in event_type or "past_due" in event_type:
            return SubscriptionStatus.past_due
        status = obj.get("status")
        return _map_status(status) if status else None
