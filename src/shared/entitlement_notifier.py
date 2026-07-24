"""Notifica al backend principal (visionpricebackend) que el plan de un
usuario cambió.

Sincroniza `Usuario.plan_activo`/`vigencia_hasta` allá (webhook ENTRANTE del
lado del backend principal — ver `POST /api/v1/pagos/callback`). Sin esto, el
pago se cobra bien en Conekta/PayPal pero el usuario nunca ve reflejado el
plan en la app ni se le habilita el audio: no es una funcionalidad opcional,
es la mitad que le faltaba a la activación.

Falla en silencio (log warning): la suscripción en Pagos ya quedó bien
guardada de cualquier forma; este aviso es best-effort. El usuario puede
consultar su estado real vía GET /subscriptions/active si este request
puntual no llega.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx

from src.shared.config import Settings

_log = logging.getLogger("pagos.entitlement")


class EntitlementNotifier:
    def __init__(self, settings: Settings):
        self._base = settings.main_api_base_url.rstrip("/")
        self._key = settings.main_api_webhook_key

    async def notificar(
        self,
        *,
        user_id: str,
        plan_key: str,
        status: str,
        current_period_end: datetime | None,
    ) -> None:
        if not self._base or not self._key:
            _log.info(
                "main_api_base_url/main_api_webhook_key no configurados — "
                "aviso de entitlement a user_id=%s omitido.",
                user_id,
            )
            return

        try:
            uid = int(user_id)
        except (TypeError, ValueError):
            _log.warning(
                "user_id no numérico (%r); no se puede notificar al backend "
                "principal (su Usuario.id es int).",
                user_id,
            )
            return

        body: dict[str, Any] = {
            "user_id": uid,
            "plan_key": plan_key,
            "status": status,
        }
        if current_period_end is not None:
            body["current_period_end"] = current_period_end.isoformat()

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self._base}/api/v1/pagos/callback",
                    json=body,
                    headers={"X-Api-Key": self._key},
                )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            _log.warning(
                "No se pudo notificar entitlement al backend principal "
                "(user_id=%s, plan=%s, status=%s): %s",
                user_id,
                plan_key,
                status,
                exc,
            )
