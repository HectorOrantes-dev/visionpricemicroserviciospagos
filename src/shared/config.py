"""Configuración central del microservicio.

Lee todas las variables desde el entorno / archivo .env usando pydantic-settings.
Es la única fuente de configuración para todos los módulos (oauth, conekta, paypal).
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- General ---
    payments_enabled: bool = True
    cors_allowed_origins: str = ""  # CSV: "https://app.visionprice.mx,https://..."

    # --- Base de datos ---
    database_url: str = "postgresql+asyncpg://payments:payments@db:5432/payments"

    # --- JWT (auth de usuarios de VisionPrice) ---
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_audience: str | None = None  # opcional; si se define se valida el claim aud

    # --- Conekta ---
    conekta_private_key: str = ""
    conekta_plan_pro: str = ""
    conekta_plan_equipos: str = ""
    conekta_api_base: str = "https://api.conekta.io"
    conekta_api_version: str = "2.1.0"

    # --- PayPal ---
    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_env: str = "sandbox"  # "sandbox" | "live"
    paypal_plan_pro: str = ""
    paypal_plan_equipos: str = ""
    paypal_webhook_id: str = ""
    paypal_brand_name: str = "Vision Price"
    paypal_return_url: str = "https://app.visionprice.mx/pagos/paypal/return"
    paypal_cancel_url: str = "https://app.visionprice.mx/pagos/paypal/cancel"

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        """Acepta el DATABASE_URL que inyecta Railway/Heroku.

        Railway entrega `postgresql://...` (o `postgres://...`); este servicio usa
        el driver async `asyncpg`, así que se reescribe el esquema. También se
        eliminan parámetros que asyncpg no entiende (`sslmode`, `channel_binding`)
        para conexiones internas que no usan SSL.
        """
        if not v:
            # .env con DATABASE_URL vacío no debe romper el arranque: usa el default.
            return "postgresql+asyncpg://payments:payments@db:5432/payments"
        if v.startswith("postgres://"):
            v = "postgresql+asyncpg://" + v[len("postgres://"):]
        elif v.startswith("postgresql://"):
            v = "postgresql+asyncpg://" + v[len("postgresql://"):]
        for bad in ("sslmode", "channel_binding"):
            # quita "?param=..." o "&param=..." que rompen a asyncpg
            import re

            v = re.sub(rf"[?&]{bad}=[^&]*", "", v)
        # si quedó un "&" inicial tras quitar el primer query param, normalízalo
        v = v.replace("?&", "?").rstrip("?&")
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        if not self.cors_allowed_origins.strip():
            return []
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def paypal_api_base(self) -> str:
        if self.paypal_env.lower() in ("live", "production", "prod"):
            return "https://api-m.paypal.com"
        return "https://api-m.sandbox.paypal.com"


@lru_cache
def get_settings() -> Settings:
    return Settings()
