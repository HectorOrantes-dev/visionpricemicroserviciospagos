"""Schemas Pydantic de entrada/salida compartidos por los routers."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from src.shared.models import Subscription


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
