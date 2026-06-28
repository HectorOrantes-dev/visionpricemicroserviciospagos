"""Middleware de cabeceras de seguridad (port del SecurityHeaders de Go/Gin).

Endurece la API contra ataques basados en navegador:
  - X-Content-Type-Options: nosniff        -> evita MIME-sniffing
  - X-Frame-Options: DENY                   -> anti-clickjacking (navegadores legacy)
  - Referrer-Policy: no-referrer            -> no filtra URLs a terceros
  - Strict-Transport-Security               -> fuerza HTTPS (solo efectivo sobre TLS)
  - Content-Security-Policy                  -> restringe qué puede cargar la respuesta

Una API JSON no sirve HTML, así que el CSP va bloqueado al máximo. Se omite para
la UI de Swagger/ReDoc (solo dev) para que sus scripts/estilos puedan cargar.

Montaje (en main.py):
    from src.shared.security_headers import SecurityHeadersMiddleware
    app.add_middleware(SecurityHeadersMiddleware)
"""
from __future__ import annotations

from collections.abc import Iterable

from starlette.datastructures import MutableHeaders

_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
# Rutas que sí necesitan cargar recursos (docs interactivas).
_CSP_EXEMPT = ("/docs", "/redoc", "/openapi.json")


class SecurityHeadersMiddleware:
    def __init__(self, app, csp_exempt_prefixes: Iterable[str] = _CSP_EXEMPT) -> None:
        self.app = app
        self._csp_exempt = tuple(csp_exempt_prefixes)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        path = scope.get("path", "")
        add_csp = not path.startswith(self._csp_exempt)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(raw=message["headers"])
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "no-referrer"
                headers["Strict-Transport-Security"] = (
                    "max-age=63072000; includeSubDomains"
                )
                if add_csp:
                    headers["Content-Security-Policy"] = _CSP
            await send(message)

        await self.app(scope, receive, send_wrapper)
