"""Excepciones de dominio y registro de handlers HTTP.

Las capas de dominio/aplicación lanzan estas excepciones agnósticas de HTTP.
`register_exception_handlers` las traduce a respuestas JSON en la capa FastAPI.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

_log = logging.getLogger("pagos.errors")


class DomainError(Exception):
    """Error de dominio base. `status_code` define el HTTP resultante."""

    status_code: int = 400
    code: str = "domain_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class PlanNotFoundError(DomainError):
    status_code = 404
    code = "plan_not_found"

    def __init__(self, plan_key: str):
        super().__init__(f"Plan desconocido: '{plan_key}'")


class SubscriptionNotFoundError(DomainError):
    status_code = 404
    code = "subscription_not_found"


class PaymentMethodNotFoundError(DomainError):
    status_code = 404
    code = "payment_method_not_found"


class CheckoutNotFoundError(DomainError):
    status_code = 404
    code = "checkout_not_found"


class AuthError(DomainError):
    status_code = 401
    code = "unauthorized"


class PaymentsDisabledError(DomainError):
    status_code = 503
    code = "payments_disabled"

    def __init__(self) -> None:
        super().__init__("Los pagos están deshabilitados (PAYMENTS_ENABLED=false).")


class ProviderError(DomainError):
    """Fallo al comunicarse con Conekta/PayPal."""

    status_code = 502
    code = "provider_error"

    def __init__(self, provider: str, message: str, details: dict | None = None):
        super().__init__(f"[{provider}] {message}")
        self.provider = provider
        self.details = details or {}


class WebhookVerificationError(DomainError):
    status_code = 400
    code = "webhook_verification_failed"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        payload = {"error": {"code": exc.code, "message": exc.message}}
        # Sin esto, un error de dominio no deja NINGÚN rastro en el log del
        # contenedor: el cliente ve el JSON, pero uvicorn solo imprime la
        # línea de acceso con el status code, nunca el motivo. >=500 como
        # error (fallo nuestro/del proveedor); <500 como warning (mala
        # petición del cliente, pero útil para diagnosticar sin reproducir).
        nivel = _log.error if exc.status_code >= 500 else _log.warning
        nivel(
            "%s %s -> %s %s: %s",
            request.method,
            request.url.path,
            exc.status_code,
            exc.code,
            exc.message,
        )
        if isinstance(exc, ProviderError) and exc.details:
            payload["error"]["details"] = exc.details
        return JSONResponse(status_code=exc.status_code, content=payload)
