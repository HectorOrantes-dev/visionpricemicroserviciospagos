"""Entidades de dominio del módulo Conekta (agnósticas de HTTP/DB)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConektaCustomer:
    """Customer creado en Conekta + tarjeta por defecto asociada."""

    customer_id: str
    default_source_id: str | None = None
    card_brand: str | None = None
    card_last4: str | None = None


@dataclass(frozen=True)
class ConektaSubscription:
    """Suscripción tal como la devuelve Conekta."""

    subscription_id: str
    status: str  # active, canceled, past_due, ...
    plan_id: str
    customer_id: str
