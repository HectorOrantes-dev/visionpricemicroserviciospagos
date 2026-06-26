"""Migración inicial: payment_customers, subscriptions, subscription_events

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-25

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

provider_enum = postgresql.ENUM(
    "conekta", "paypal", name="provider_enum", create_type=False
)
status_enum = postgresql.ENUM(
    "pending",
    "active",
    "past_due",
    "cancelled",
    "expired",
    name="subscription_status_enum",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    provider_enum.create(bind, checkfirst=True)
    status_enum.create(bind, checkfirst=True)

    op.create_table(
        "payment_customers",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=False, index=True),
        sa.Column("provider", provider_enum, nullable=False),
        sa.Column("provider_customer_id", sa.String(length=128), nullable=False),
        sa.Column("card_brand", sa.String(length=32), nullable=True),
        sa.Column("card_last4", sa.String(length=4), nullable=True),
        sa.Column("default_source_id", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=False, index=True),
        sa.Column("provider", provider_enum, nullable=False),
        sa.Column("plan_key", sa.String(length=64), nullable=False),
        sa.Column(
            "provider_subscription_id",
            sa.String(length=128),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "status",
            status_enum,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "subscription_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "subscription_id",
            sa.String(length=36),
            sa.ForeignKey("subscriptions.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column(
            "raw_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("subscription_events")
    op.drop_table("subscriptions")
    op.drop_table("payment_customers")
    bind = op.get_bind()
    status_enum.drop(bind, checkfirst=True)
    provider_enum.drop(bind, checkfirst=True)
