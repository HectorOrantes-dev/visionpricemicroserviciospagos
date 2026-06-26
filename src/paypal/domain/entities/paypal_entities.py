"""Entidades de dominio del módulo PayPal."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PayPalSubscription:
    subscription_id: str
    status: str  # APPROVAL_PENDING, ACTIVE, CANCELLED, EXPIRED, SUSPENDED
    approval_url: str | None = None
