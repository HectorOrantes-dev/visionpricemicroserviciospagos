"""Middleware de validación del API Gateway (fase de rollout OPCIONAL).

Montaje (en main.py):
    from src.shared.gateway_key import GatewayKeyMiddleware
    app.add_middleware(GatewayKeyMiddleware, settings=settings)

Comportamiento actual (dual-accept, para no romper producción mientras el
móvil todavía le pega directo a este servicio en vez de al gateway):
  - settings.gateway_shared_key vacío       -> no-op total (como hoy).
  - Header X-Gateway-Key AUSENTE            -> deja pasar igual (rollout).
  - Header X-Gateway-Key PRESENTE pero mal  -> 401, corta acá.
  - Header X-Gateway-Key PRESENTE y OK      -> pasa.

Los webhooks de Conekta/PayPal quedan EXCLUIDOS siempre: esos los llama el
proveedor de pagos directo, jamás van a traer X-Gateway-Key.

Cuando el móvil ya solo le pegue al gateway, cambiar la rama "ausente" para
que también rechace — ese es el modo estricto (un cambio de una línea acá).
"""
from __future__ import annotations

import hmac
import json

_EXCLUIDOS = ("/health", "/conekta/webhook", "/paypal/webhook")


class GatewayKeyMiddleware:
    def __init__(self, app, settings) -> None:
        self.app = app
        self._settings = settings

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not self._settings.gateway_shared_key:
            return await self.app(scope, receive, send)

        path = scope.get("path", "")
        if path in _EXCLUIDOS:
            return await self.app(scope, receive, send)

        recibida = _header(scope, b"x-gateway-key")
        if recibida is not None and not hmac.compare_digest(
            recibida.decode(), self._settings.gateway_shared_key
        ):
            return await _rechazar(send)

        return await self.app(scope, receive, send)


def _header(scope, nombre: bytes) -> bytes | None:
    for k, v in scope["headers"]:
        if k == nombre:
            return v
    return None


async def _rechazar(send) -> None:
    body = json.dumps(
        {"error": {"code": "unauthorized", "message": "X-Gateway-Key inválida."}}
    ).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": body})
