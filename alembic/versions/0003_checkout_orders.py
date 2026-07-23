"""Tabla checkout_orders (Conekta Checkout: tarjeta, OXXO, SPEI)

Revision ID: 0003_checkout_orders
Revises: 0002_idempotency_keys
Create Date: 2026-07-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_checkout_orders"
down_revision: Union[str, None] = "0002_idempotency_keys"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

provider_enum = postgresql.ENUM(
    "conekta", "paypal", name="provider_enum", create_type=False
)
checkout_status_enum = postgresql.ENUM(
    "pending",
    "paid",
    "expired",
    "cancelled",
    name="checkout_status_enum",
)


def upgrade() -> None:
    bind = op.get_bind()
    checkout_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "checkout_orders",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=False, index=True),
        sa.Column("provider", provider_enum, nullable=False),
        sa.Column("plan_key", sa.String(length=64), nullable=False),
        sa.Column(
            "checkout_id", sa.String(length=128), nullable=False, unique=True, index=True
        ),
        sa.Column("checkout_url", sa.String(length=512), nullable=False),
        sa.Column(
            "provider_order_id", sa.String(length=128), nullable=True, index=True
        ),
        sa.Column(
            "status",
            checkout_status_enum,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("payment_method", sa.String(length=32), nullable=True),
        sa.Column("amount_mxn", sa.Integer, nullable=False),
        sa.Column(
            "currency", sa.String(length=8), nullable=False, server_default="MXN"
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("checkout_orders")
    bind = op.get_bind()
    checkout_status_enum.drop(bind, checkfirst=True)
