"""Dependencias FastAPI de autenticación.

`get_current_user` extrae el Bearer token, lo verifica y devuelve el AuthenticatedUser.
Se reutiliza en todos los routers protegidos (conekta, paypal, historial).
"""
from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.oauth.domain.authenticated_user import AuthenticatedUser
from src.oauth.infraestructure.adapters.jwt_verifier import JwtVerifier
from src.shared.config import Settings, get_settings
from src.shared.errors import AuthError, PaymentsDisabledError

_bearer = HTTPBearer(auto_error=False)


def get_jwt_verifier(settings: Settings = Depends(get_settings)) -> JwtVerifier:
    return JwtVerifier(settings)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    verifier: JwtVerifier = Depends(get_jwt_verifier),
    settings: Settings = Depends(get_settings),
) -> AuthenticatedUser:
    if not settings.payments_enabled:
        raise PaymentsDisabledError()
    if credentials is None or not credentials.credentials:
        raise AuthError("Falta el header Authorization: Bearer <token>.")
    return verifier.verify(credentials.credentials)
