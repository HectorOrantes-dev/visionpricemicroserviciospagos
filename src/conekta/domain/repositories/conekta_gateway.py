"""Puerto del gateway de Conekta (interfaz que el adaptador HTTP implementa)."""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.conekta.domain.entities.conekta_entities import (
    ConektaCheckout,
    ConektaCustomer,
    ConektaSubscription,
)


class ConektaGatewayPort(ABC):
    @abstractmethod
    async def create_customer(
        self, *, name: str, email: str | None, card_token: str
    ) -> ConektaCustomer: ...

    @abstractmethod
    async def add_card(
        self, customer_id: str, card_token: str
    ) -> ConektaCustomer: ...

    @abstractmethod
    async def delete_source(self, customer_id: str, source_id: str) -> None: ...

    @abstractmethod
    async def create_subscription(
        self, customer_id: str, plan_id: str
    ) -> ConektaSubscription: ...

    @abstractmethod
    async def cancel_subscription(
        self, customer_id: str
    ) -> ConektaSubscription: ...

    @abstractmethod
    async def create_checkout(
        self,
        *,
        name: str,
        amount_cents: int,
        currency: str,
        allowed_payment_methods: list[str],
        customer_name: str,
        customer_email: str | None,
        expires_at: int,
        metadata: dict,
    ) -> ConektaCheckout: ...
