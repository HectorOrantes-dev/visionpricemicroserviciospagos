"""Implementación SQLAlchemy (async) de los puertos de persistencia."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.models import (
    CheckoutOrder,
    CheckoutStatus,
    PaymentCustomer,
    Provider,
    Subscription,
    SubscriptionEvent,
    SubscriptionStatus,
)
from src.shared.repositories import (
    CheckoutOrderRepositoryPort,
    CustomerRepositoryPort,
    SubscriptionRepositoryPort,
)

_ACTIVE_STATES = (SubscriptionStatus.active, SubscriptionStatus.pending)


class SqlSubscriptionRepository(SubscriptionRepositoryPort):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(self, subscription: Subscription) -> Subscription:
        self._session.add(subscription)
        await self._session.commit()
        await self._session.refresh(subscription)
        return subscription

    async def get(self, subscription_id: str) -> Subscription | None:
        return await self._session.get(Subscription, subscription_id)

    async def get_for_user(
        self, subscription_id: str, user_id: str
    ) -> Subscription | None:
        sub = await self._session.get(Subscription, subscription_id)
        if sub is None or sub.user_id != user_id:
            return None
        return sub

    async def get_by_provider_id(
        self, provider: Provider, provider_subscription_id: str
    ) -> Subscription | None:
        stmt = select(Subscription).where(
            Subscription.provider == provider,
            Subscription.provider_subscription_id == provider_subscription_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_for_user(
        self, user_id: str, provider: Provider | None = None
    ) -> list[Subscription]:
        stmt = select(Subscription).where(Subscription.user_id == user_id)
        if provider is not None:
            stmt = stmt.where(Subscription.provider == provider)
        stmt = stmt.order_by(Subscription.created_at.desc())
        return list((await self._session.execute(stmt)).scalars().all())

    async def get_active_for_user(
        self, user_id: str, provider: Provider
    ) -> Subscription | None:
        stmt = (
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.provider == provider,
                Subscription.status.in_(_ACTIVE_STATES),
            )
            .order_by(Subscription.created_at.desc())
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def update_status(
        self,
        subscription: Subscription,
        status: SubscriptionStatus,
        *,
        current_period_end: datetime | None = None,
        cancelled_at: datetime | None = None,
    ) -> Subscription:
        subscription.status = status
        if current_period_end is not None:
            subscription.current_period_end = current_period_end
        if cancelled_at is not None:
            subscription.cancelled_at = cancelled_at
        await self._session.commit()
        await self._session.refresh(subscription)
        return subscription

    async def record_event(
        self, subscription: Subscription, event_type: str, raw_payload: dict
    ) -> None:
        self._session.add(
            SubscriptionEvent(
                subscription_id=subscription.id,
                event_type=event_type,
                raw_payload=raw_payload,
            )
        )
        await self._session.commit()


class SqlCustomerRepository(CustomerRepositoryPort):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self, user_id: str, provider: Provider) -> PaymentCustomer | None:
        stmt = select(PaymentCustomer).where(
            PaymentCustomer.user_id == user_id,
            PaymentCustomer.provider == provider,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def add(self, customer: PaymentCustomer) -> PaymentCustomer:
        self._session.add(customer)
        await self._session.commit()
        await self._session.refresh(customer)
        return customer

    async def save(self, customer: PaymentCustomer) -> PaymentCustomer:
        await self._session.commit()
        await self._session.refresh(customer)
        return customer

    async def delete_card(self, customer: PaymentCustomer) -> None:
        customer.card_brand = None
        customer.card_last4 = None
        customer.default_source_id = None
        await self._session.commit()


class SqlCheckoutOrderRepository(CheckoutOrderRepositoryPort):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(self, order: CheckoutOrder) -> CheckoutOrder:
        self._session.add(order)
        await self._session.commit()
        await self._session.refresh(order)
        return order

    async def get(self, checkout_db_id: str) -> CheckoutOrder | None:
        return await self._session.get(CheckoutOrder, checkout_db_id)

    async def get_for_user(
        self, checkout_db_id: str, user_id: str
    ) -> CheckoutOrder | None:
        order = await self._session.get(CheckoutOrder, checkout_db_id)
        if order is None or order.user_id != user_id:
            return None
        return order

    async def get_by_checkout_id(self, checkout_id: str) -> CheckoutOrder | None:
        stmt = select(CheckoutOrder).where(CheckoutOrder.checkout_id == checkout_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def update_status(
        self,
        order: CheckoutOrder,
        status: CheckoutStatus,
        *,
        payment_method: str | None = None,
        provider_order_id: str | None = None,
        paid_at: datetime | None = None,
    ) -> CheckoutOrder:
        order.status = status
        if payment_method is not None:
            order.payment_method = payment_method
        if provider_order_id is not None:
            order.provider_order_id = provider_order_id
        if paid_at is not None:
            order.paid_at = paid_at
        await self._session.commit()
        await self._session.refresh(order)
        return order
