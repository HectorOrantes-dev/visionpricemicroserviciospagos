"""Adaptador HTTP del gateway de Conekta (api.conekta.io) usando httpx.

El cambio test↔producción es transparente: solo depende de `CONEKTA_PRIVATE_KEY`
(key de test vs key_live_... de producción), no del código.
"""
from __future__ import annotations

from typing import Any

import httpx

from src.conekta.domain.entities.conekta_entities import (
    ConektaCustomer,
    ConektaSubscription,
)
from src.conekta.domain.repositories.conekta_gateway import ConektaGatewayPort
from src.shared.config import Settings
from src.shared.errors import ProviderError


class ConektaHttpClient(ConektaGatewayPort):
    def __init__(self, settings: Settings):
        self._base = settings.conekta_api_base.rstrip("/")
        self._auth = httpx.BasicAuth(settings.conekta_private_key, "")
        self._headers = {
            "Accept": f"application/vnd.conekta-v{settings.conekta_api_version}+json",
            "Content-Type": "application/json",
        }

    async def _request(
        self, method: str, path: str, json: dict | None = None
    ) -> dict[str, Any]:
        url = f"{self._base}{path}"
        try:
            async with httpx.AsyncClient(
                auth=self._auth, headers=self._headers, timeout=30.0
            ) as client:
                resp = await client.request(method, url, json=json)
        except httpx.HTTPError as exc:
            raise ProviderError("conekta", f"Error de red: {exc}") from exc

        if resp.status_code >= 400:
            try:
                body = resp.json()
            except Exception:
                body = {"raw": resp.text}
            message = "Solicitud rechazada por Conekta"
            details = body.get("details") if isinstance(body, dict) else None
            if details:
                message = "; ".join(
                    d.get("message", "") for d in details if isinstance(d, dict)
                ) or message
            raise ProviderError("conekta", message, details=body)

        return resp.json() if resp.content else {}

    @staticmethod
    def _extract_card(data: dict) -> tuple[str | None, str | None, str | None]:
        sources = (data.get("payment_sources") or {}).get("data") or []
        if not sources:
            return None, None, None
        src = sources[0]
        return src.get("id"), src.get("brand"), src.get("last4")

    async def create_customer(
        self, *, name: str, email: str | None, card_token: str
    ) -> ConektaCustomer:
        body: dict[str, Any] = {
            "name": name,
            "payment_sources": [{"type": "card", "token_id": card_token}],
        }
        if email:
            body["email"] = email
        data = await self._request("POST", "/customers", json=body)
        source_id, brand, last4 = self._extract_card(data)
        return ConektaCustomer(
            customer_id=data["id"],
            default_source_id=source_id,
            card_brand=brand,
            card_last4=last4,
        )

    async def add_card(self, customer_id: str, card_token: str) -> ConektaCustomer:
        data = await self._request(
            "POST",
            f"/customers/{customer_id}/payment_sources",
            json={"type": "card", "token_id": card_token},
        )
        return ConektaCustomer(
            customer_id=customer_id,
            default_source_id=data.get("id"),
            card_brand=data.get("brand"),
            card_last4=data.get("last4"),
        )

    async def delete_source(self, customer_id: str, source_id: str) -> None:
        await self._request(
            "DELETE", f"/customers/{customer_id}/payment_sources/{source_id}"
        )

    async def create_subscription(
        self, customer_id: str, plan_id: str
    ) -> ConektaSubscription:
        data = await self._request(
            "POST",
            f"/customers/{customer_id}/subscription",
            json={"plan_id": plan_id},
        )
        return ConektaSubscription(
            subscription_id=data.get("id", ""),
            status=data.get("status", "active"),
            plan_id=plan_id,
            customer_id=customer_id,
        )

    async def cancel_subscription(self, customer_id: str) -> ConektaSubscription:
        data = await self._request(
            "POST", f"/customers/{customer_id}/subscription/cancel"
        )
        return ConektaSubscription(
            subscription_id=data.get("id", ""),
            status=data.get("status", "canceled"),
            plan_id=data.get("plan_id", ""),
            customer_id=customer_id,
        )
