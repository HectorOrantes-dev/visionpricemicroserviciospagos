"""Entidad de dominio: usuario autenticado a partir del JWT de VisionPrice."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuthenticatedUser:
    """Representa al usuario identificado por el JWT.

    `user_id` proviene del claim `sub`. `email` es opcional (claim `email`).
    """

    user_id: str
    email: str | None = None
    claims: dict | None = None
