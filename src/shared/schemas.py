"""Schemas Pydantic de entrada/salida compartidos por los routers."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from src.shared.models import CheckoutOrder, Subscription


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    provider: str
    plan_key: str
    provider_subscription_id: str | None
    status: str
    current_period_end: datetime | None
    created_at: datetime
    cancelled_at: datetime | None

    @classmethod
    def of(cls, sub: Subscription) -> "SubscriptionOut":
        return cls(
            id=sub.id,
            user_id=sub.user_id,
            provider=sub.provider.value,
            plan_key=sub.plan_key,
            provider_subscription_id=sub.provider_subscription_id,
            status=sub.status.value,
            current_period_end=sub.current_period_end,
            created_at=sub.created_at,
            cancelled_at=sub.cancelled_at,
        )


class CheckoutOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    plan_key: str
    checkout_id: str
    checkout_url: str
    status: str
    payment_method: str | None
    amount_mxn: int
    currency: str
    expires_at: datetime | None
    created_at: datetime
    paid_at: datetime | None

    @classmethod
    def of(cls, order: CheckoutOrder) -> "CheckoutOut":
        return cls(
            id=order.id,
            plan_key=order.plan_key,
            checkout_id=order.checkout_id,
            checkout_url=order.checkout_url,
            status=order.status.value,
            payment_method=order.payment_method,
            amount_mxn=order.amount_mxn,
            currency=order.currency,
            expires_at=order.expires_at,
            created_at=order.created_at,
            paid_at=order.paid_at,
        )
