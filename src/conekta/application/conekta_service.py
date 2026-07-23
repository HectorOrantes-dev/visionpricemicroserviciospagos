"""Casos de uso del módulo Conekta (orquestan gateway + persistencia).

Dependen solo de puertos (ConektaGatewayPort, SubscriptionRepositoryPort,
CustomerRepositoryPort), nunca de httpx/SQLAlchemy directamente.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from src.conekta.domain.repositories.conekta_gateway import ConektaGatewayPort
from src.oauth.domain.authenticated_user import AuthenticatedUser
from src.shared.config import Settings
from src.shared.errors import (
    CheckoutNotFoundError,
    DomainError,
    PaymentMethodNotFoundError,
    SubscriptionNotFoundError,
)
from src.shared.models import (
    CheckoutOrder,
    CheckoutStatus,
    PaymentCustomer,
    Provider,
    Subscription,
    SubscriptionStatus,
)
from src.shared.plan_catalog import get_plan
from src.shared.repositories import (
    CheckoutOrderRepositoryPort,
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
        checkouts: CheckoutOrderRepositoryPort,
        settings: Settings,
    ):
        self._gateway = gateway
        self._subs = subscriptions
        self._customers = customers
        self._checkouts = checkouts
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

    async def create_checkout(
        self,
        user: AuthenticatedUser,
        plan_key: str,
        allowed_payment_methods: list[str] | None = None,
    ) -> CheckoutOrder:
        """Crea un link de pago (Conekta Checkout): tarjeta, OXXO o SPEI.

        No es recurrente. Cuando Conekta confirma el pago (webhook
        `order.paid`), `_grant_period` otorga `plan.period_days` de vigencia
        sobre la suscripción del usuario (crea una si no existía, o la
        extiende si ya tenía una activa).
        """
        plan = get_plan(plan_key, self._settings)
        methods = (
            allowed_payment_methods
            or self._settings.conekta_checkout_payment_methods_list
        )

        # Generado ANTES de llamar a Conekta para poder correlacionar el
        # webhook contra esta orden vía metadata, sin depender de la forma
        # exacta en que Conekta anide el id del checkout dentro del order.
        internal_ref = str(uuid.uuid4())
        expires_dt = _now() + timedelta(
            hours=self._settings.conekta_checkout_expires_hours
        )

        remote = await self._gateway.create_checkout(
            name=plan.description,
            amount_cents=plan.price_mxn * 100,
            currency=plan.currency,
            allowed_payment_methods=methods,
            customer_name=user.email or user.user_id,
            customer_email=user.email,
            expires_at=int(expires_dt.timestamp()),
            metadata={"internal_ref": internal_ref, "user_id": user.user_id},
        )

        order = CheckoutOrder(
            id=internal_ref,
            user_id=user.user_id,
            provider=Provider.conekta,
            plan_key=plan_key,
            checkout_id=remote.checkout_id,
            checkout_url=remote.checkout_url,
            amount_mxn=plan.price_mxn,
            currency=plan.currency,
            expires_at=expires_dt,
        )
        return await self._checkouts.add(order)

    async def get_checkout(
        self, user: AuthenticatedUser, checkout_db_id: str
    ) -> CheckoutOrder:
        order = await self._checkouts.get_for_user(checkout_db_id, user.user_id)
        if order is None:
            raise CheckoutNotFoundError("Checkout no encontrado.")
        return order

    async def _grant_period(
        self, order: CheckoutOrder, period_days: int
    ) -> Subscription:
        now = _now()
        existing = await self._subs.get_active_for_user(
            order.user_id, Provider.conekta
        )
        if existing is not None and existing.plan_key == order.plan_key:
            base = (
                existing.current_period_end
                if existing.current_period_end and existing.current_period_end > now
                else now
            )
            subscription = await self._subs.update_status(
                existing,
                SubscriptionStatus.active,
                current_period_end=base + timedelta(days=period_days),
            )
        else:
            subscription = await self._subs.add(
                Subscription(
                    user_id=order.user_id,
                    provider=Provider.conekta,
                    plan_key=order.plan_key,
                    provider_subscription_id=None,
                    status=SubscriptionStatus.active,
                )
            )
            subscription = await self._subs.update_status(
                subscription,
                SubscriptionStatus.active,
                current_period_end=now + timedelta(days=period_days),
            )
        await self._subs.record_event(
            subscription,
            "checkout.paid",
            {"checkout_id": order.checkout_id, "payment_method": order.payment_method},
        )
        return subscription

    async def handle_webhook(self, event: dict) -> None:
        """Procesa un evento de webhook de Conekta y actualiza el estado."""
        event_type = event.get("type", "unknown")
        obj = ((event.get("data") or {}).get("object")) or {}
        obj_type = obj.get("object")

        if obj_type == "order" or event_type.startswith(("order.", "checkout.")):
            await self._handle_order_webhook(event_type, obj)
            return

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

    async def _handle_order_webhook(self, event_type: str, obj: dict) -> None:
        """Procesa eventos de una orden creada vía Checkout (tarjeta/OXXO/SPEI)."""
        internal_ref = (obj.get("metadata") or {}).get("internal_ref")
        order: CheckoutOrder | None = None
        if internal_ref:
            order = await self._checkouts.get(internal_ref)
        if order is None:
            # Sin metadata (p.ej. evento de prueba desde el dashboard) o
            # checkout no encontrado: no hay nada que actualizar.
            return

        if order.status == CheckoutStatus.paid:
            return  # ya procesado; evita duplicar la vigencia otorgada

        if "paid" in event_type or obj.get("payment_status") == "paid":
            charges = (obj.get("charges") or {}).get("data") or []
            payment_method = None
            if charges:
                # `payment_method.type` trae "credit"/"debit" para tarjeta (no
                # "card"), así que se deriva del `object`: "card_payment" ->
                # "card", "cash_payment" -> "cash", "bank_transfer_payment"
                # -> "bank_transfer". Verificado contra un charge real del
                # sandbox (2026-07-23).
                pm = charges[0].get("payment_method") or {}
                pm_object = pm.get("object", "")
                payment_method = (
                    pm_object.removesuffix("_payment") if pm_object else pm.get("type")
                )
            order = await self._checkouts.update_status(
                order,
                CheckoutStatus.paid,
                payment_method=payment_method,
                provider_order_id=obj.get("id"),
                paid_at=_now(),
            )
            plan = get_plan(order.plan_key, self._settings)
            await self._grant_period(order, plan.period_days)
        elif "expired" in event_type:
            await self._checkouts.update_status(order, CheckoutStatus.expired)
        elif "canceled" in event_type or "cancelled" in event_type:
            await self._checkouts.update_status(order, CheckoutStatus.cancelled)

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
