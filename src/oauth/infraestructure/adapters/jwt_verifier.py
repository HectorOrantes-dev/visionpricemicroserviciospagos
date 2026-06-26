"""Adaptador de verificación de JWT (HS256) emitido por VisionPrice.

Este microservicio NO emite tokens: solo valida el JWT con `JWT_SECRET` para
identificar al usuario y asociarle sus suscripciones.
"""
from __future__ import annotations

import jwt

from src.oauth.domain.authenticated_user import AuthenticatedUser
from src.shared.config import Settings
from src.shared.errors import AuthError


class JwtVerifier:
    def __init__(self, settings: Settings):
        self._secret = settings.jwt_secret
        self._algorithm = settings.jwt_algorithm
        self._audience = settings.jwt_audience

    def verify(self, token: str) -> AuthenticatedUser:
        options = {"require": ["sub"]}
        try:
            claims = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                audience=self._audience if self._audience else None,
                options={
                    **options,
                    "verify_aud": bool(self._audience),
                },
            )
        except jwt.ExpiredSignatureError as exc:
            raise AuthError("El token ha expirado.") from exc
        except jwt.InvalidTokenError as exc:
            raise AuthError("Token inválido.") from exc

        user_id = claims.get("sub")
        if not user_id:
            raise AuthError("El token no contiene 'sub' (id de usuario).")

        return AuthenticatedUser(
            user_id=str(user_id),
            email=claims.get("email"),
            claims=claims,
        )
