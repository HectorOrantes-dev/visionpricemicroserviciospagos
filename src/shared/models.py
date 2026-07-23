"""Modelos ORM (PostgreSQL) compartidos por los módulos de pago.

Tres tablas:
- payment_customers: usuario ↔ customer del proveedor + tarjeta asociada.
- subscriptions: una fila por suscripción (núcleo + historial de mensualidades).
- subscription_events: bitácora de webhooks y cambios de estado (auditoría).
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.shared.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Provider(str, enum.Enum):
    conekta = "conekta"
    paypal = "paypal"


class SubscriptionStatus(str, enum.Enum):
    pending = "pending"        # creada, esperando aprobación/pago (PayPal)
    active = "active"          # mensualidad activa
    past_due = "past_due"      # pago fallido, en gracia
    cancelled = "cancelled"    # cancelada por el usuario
    expired = "expired"        # terminada


class CheckoutStatus(str, enum.Enum):
    pending = "pending"    # link creado, esperando que el usuario pague
    paid = "paid"          # Conekta confirmó el pago (order.paid)
    expired = "expired"    # venció sin pagarse (referencia OXXO/SPEI caducada)
    cancelled = "cancelled"


class PaymentCustomer(Base):
    __tablename__ = "payment_customers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    provider: Mapped[Provider] = mapped_column(
        SAEnum(Provider, name="provider_enum"), nullable=False
    )
    provider_customer_id: Mapped[str] = mapped_column(String(128), nullable=False)
    card_brand: Mapped[str | None] = mapped_column(String(32), nullable=True)
    card_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    default_source_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    provider: Mapped[Provider] = mapped_column(
        SAEnum(Provider, name="provider_enum"), nullable=False
    )
    plan_key: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_subscription_id: Mapped[str | None] = mapped_column(
        String(128), index=True, nullable=True
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        SAEnum(SubscriptionStatus, name="subscription_status_enum"),
        default=SubscriptionStatus.pending,
        nullable=False,
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    events: Mapped[list["SubscriptionEvent"]] = relationship(
        back_populates="subscription",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class SubscriptionEvent(Base):
    __tablename__ = "subscription_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    subscription_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("subscriptions.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    subscription: Mapped[Subscription] = relationship(back_populates="events")


class CheckoutOrder(Base):
    """Link de pago (Conekta Checkout) para tarjeta, OXXO o SPEI.

    A diferencia de `Subscription`, no es recurrente: Conekta no puede
    volver a cobrar solo automáticamente ni con OXXO ni con SPEI. Cada
    checkout pagado otorga `plan.period_days` de vigencia (ver
    ConektaService._grant_period); el usuario debe generar un checkout
    nuevo para renovar cuando expira.
    """

    __tablename__ = "checkout_orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    provider: Mapped[Provider] = mapped_column(
        SAEnum(Provider, name="provider_enum"), nullable=False
    )
    plan_key: Mapped[str] = mapped_column(String(64), nullable=False)
    checkout_id: Mapped[str] = mapped_column(
        String(128), unique=True, index=True, nullable=False
    )
    checkout_url: Mapped[str] = mapped_column(String(512), nullable=False)
    provider_order_id: Mapped[str | None] = mapped_column(
        String(128), index=True, nullable=True
    )
    status: Mapped[CheckoutStatus] = mapped_column(
        SAEnum(CheckoutStatus, name="checkout_status_enum"),
        default=CheckoutStatus.pending,
        nullable=False,
    )
    payment_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    amount_mxn: Mapped[int] = mapped_column(nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="MXN", nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
