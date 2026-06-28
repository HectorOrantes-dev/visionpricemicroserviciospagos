"""Tabla idempotency_keys (middleware de idempotencia)

Revision ID: 0002_idempotency_keys
Revises: 0001_initial
Create Date: 2026-06-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_idempotency_keys"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("clave", sa.String(length=255), nullable=False),
        # user_id del JWT (claim sub) -> string en este micro
        sa.Column("usuario_id", sa.String(length=128), nullable=True),
        sa.Column("metodo", sa.String(length=10), nullable=False),
        sa.Column("ruta", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "estado",
            sa.String(length=20),
            nullable=False,
            server_default="procesando",
        ),
        sa.Column("status_code", sa.Integer, nullable=True),
        sa.Column("content_type", sa.String(length=100), nullable=True),
        sa.Column("response_body", sa.Text, nullable=True),
        sa.Column(
            "fecha_creacion",
            sa.DateTime,
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "fecha_actualizacion",
            sa.DateTime,
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_idempotency_clave", "idempotency_keys", ["clave"], unique=True
    )


def downgrade() -> None:
    op.drop_index("idx_idempotency_clave", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")
