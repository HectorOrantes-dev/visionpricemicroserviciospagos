"""Punto de entrada del microservicio de pasarela de pagos (VisionPrice).

App factory de FastAPI: monta los routers de cada módulo (conekta, paypal y el
historial común), configura CORS y los handlers de error de dominio.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.conekta.infraestructure.routers.conekta_router import (
    router as conekta_router,
)
from src.oauth.infraestructure.adapters.jwt_verifier import JwtVerifier
from src.paypal.infraestructure.routers.paypal_router import router as paypal_router
from src.shared.config import get_settings
from src.shared.database import SessionLocal
from src.shared.errors import register_exception_handlers
from src.shared.idempotency import IdempotencyMiddleware
from src.shared.security_headers import SecurityHeadersMiddleware
from src.shared.subscriptions_router import router as subscriptions_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Las tablas se crean/migran con Alembic (ver alembic/). Aquí solo
    # se delimita el ciclo de vida de la app.
    yield


def _extract_user_id(settings):
    """Devuelve un extractor scope->user_id (claim sub) best-effort para idempotencia.

    No rompe la petición si el token falta o es inválido (devuelve None); la
    verificación real la siguen haciendo las dependencias de cada ruta.
    """
    verifier = JwtVerifier(settings)

    def extractor(scope) -> str | None:
        for k, v in scope.get("headers", []):
            if k == b"authorization":
                token = v.decode().removeprefix("Bearer ").strip()
                try:
                    return verifier.verify(token).user_id
                except Exception:
                    return None
        return None

    return extractor


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="VisionPrice — Pasarela de Pagos",
        description="Microservicio de suscripciones (Conekta + PayPal).",
        version="1.0.0",
        lifespan=lifespan,
    )

    if settings.cors_origins_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    register_exception_handlers(app)

    # Cabeceras de seguridad en todas las respuestas (más externo).
    app.add_middleware(SecurityHeadersMiddleware)

    # Idempotencia: solo POST/PUT/PATCH con header `Idempotency-Key`.
    app.add_middleware(
        IdempotencyMiddleware,
        session_factory=SessionLocal,
        user_id_extractor=_extract_user_id(settings),
    )

    app.include_router(conekta_router)
    app.include_router(paypal_router)
    app.include_router(subscriptions_router)

    @app.get("/health", tags=["health"])
    async def health() -> dict:
        return {
            "status": "ok",
            "payments_enabled": settings.payments_enabled,
            "paypal_env": settings.paypal_env,
        }

    return app


app = create_app()
