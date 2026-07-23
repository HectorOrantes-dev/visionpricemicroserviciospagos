"""Puertos de persistencia (interfaces) — capa de dominio compartida.

Los casos de uso de conekta y paypal dependen de estas abstracciones, no de
SQLAlchemy. La implementación concreta vive en `sql_repository.py`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from src.shared.models import (
    CheckoutOrder,
    CheckoutStatus,
    PaymentCustomer,
    Provider,
    Subscription,
    SubscriptionStatus,
)


class SubscriptionRepositoryPort(ABC):
    @abstractmethod
    async def add(self, subscription: Subscription) -> Subscription: ...

    @abstractmethod
    async def get(self, subscription_id: str) -> Subscription | None: ...

    @abstractmethod
    async def get_for_user(
        self, subscription_id: str, user_id: str
    ) -> Subscription | None: ...

    @abstractmethod
    async def get_by_provider_id(
        self, provider: Provider, provider_subscription_id: str
    ) -> Subscription | None: ...

    @abstractmethod
    async def list_for_user(
        self, user_id: str, provider: Provider | None = None
    ) -> list[Subscription]: ...

    @abstractmethod
    async def get_active_for_user(
        self, user_id: str, provider: Provider
    ) -> Subscription | None: ...

    @abstractmethod
    async def update_status(
        self,
        subscription: Subscription,
        status: SubscriptionStatus,
        *,
        current_period_end: datetime | None = None,
        cancelled_at: datetime | None = None,
    ) -> Subscription: ...

    @abstractmethod
    async def record_event(
        self, subscription: Subscription, event_type: str, raw_payload: dict
    ) -> None: ...


class CustomerRepositoryPort(ABC):
    @abstractmethod
    async def get(
        self, user_id: str, provider: Provider
    ) -> PaymentCustomer | None: ...

    @abstractmethod
    async def add(self, customer: PaymentCustomer) -> PaymentCustomer: ...

    @abstractmethod
    async def save(self, customer: PaymentCustomer) -> PaymentCustomer: ...

    @abstractmethod
    async def delete_card(self, customer: PaymentCustomer) -> None: ...


class CheckoutOrderRepositoryPort(ABC):
    @abstractmethod
    async def add(self, order: CheckoutOrder) -> CheckoutOrder: ...

    @abstractmethod
    async def get(self, checkout_db_id: str) -> CheckoutOrder | None: ...

    @abstractmethod
    async def get_for_user(
        self, checkout_db_id: str, user_id: str
    ) -> CheckoutOrder | None: ...

    @abstractmethod
    async def get_by_checkout_id(self, checkout_id: str) -> CheckoutOrder | None: ...

    @abstractmethod
    async def update_status(
        self,
        order: CheckoutOrder,
        status: CheckoutStatus,
        *,
        payment_method: str | None = None,
        provider_order_id: str | None = None,
        paid_at: datetime | None = None,
    ) -> CheckoutOrder: ...
