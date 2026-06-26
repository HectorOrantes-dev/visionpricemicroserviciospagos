"""Puerto del gateway de PayPal (implementado por el adaptador HTTP)."""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.paypal.domain.entities.paypal_entities import PayPalSubscription


class PayPalGatewayPort(ABC):
    @abstractmethod
    async def create_subscription(
        self, *, plan_id: str, user_id: str, email: str | None
    ) -> PayPalSubscription: ...

    @abstractmethod
    async def get_subscription(self, subscription_id: str) -> PayPalSubscription: ...

    @abstractmethod
    async def cancel_subscription(
        self, subscription_id: str, reason: str
    ) -> None: ...

    @abstractmethod
    async def verify_webhook(self, headers: dict, body: dict) -> bool: ...
