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
from src.paypal.infraestructure.routers.paypal_router import router as paypal_router
from src.shared.config import get_settings
from src.shared.errors import register_exception_handlers
from src.shared.subscriptions_router import router as subscriptions_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Las tablas se crean/migran con Alembic (ver alembic/). Aquí solo
    # se delimita el ciclo de vida de la app.
    yield


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
