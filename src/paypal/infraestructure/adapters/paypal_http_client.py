"""Adaptador HTTP del gateway de PayPal (REST v1) con cache de token OAuth.

Cambia entre sandbox y producción según `PAYPAL_ENV` (settings.paypal_api_base).
"""
from __future__ import annotations

import time
from typing import Any

import httpx

from src.paypal.domain.entities.paypal_entities import PayPalSubscription
from src.paypal.domain.repositories.paypal_gateway import PayPalGatewayPort
from src.shared.config import Settings
from src.shared.errors import ProviderError


class PayPalHttpClient(PayPalGatewayPort):
    # Cache de token a nivel de clase (compartido entre requests del proceso).
    _token: str | None = None
    _token_exp: float = 0.0

    def __init__(self, settings: Settings):
        self._settings = settings
        self._base = settings.paypal_api_base.rstrip("/")
        self._auth = (settings.paypal_client_id, settings.paypal_client_secret)

    async def _get_token(self) -> str:
        now = time.time()
        if PayPalHttpClient._token and now < PayPalHttpClient._token_exp:
            return PayPalHttpClient._token
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self._base}/v1/oauth2/token",
                    auth=self._auth,
                    data={"grant_type": "client_credentials"},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
        except httpx.HTTPError as exc:
            raise ProviderError("paypal", f"Error de red en OAuth: {exc}") from exc
        if resp.status_code >= 400:
            raise ProviderError(
                "paypal", "No se pudo obtener el token OAuth", details=_safe_json(resp)
            )
        data = resp.json()
        PayPalHttpClient._token = data["access_token"]
        # Renueva 60s antes de expirar.
        PayPalHttpClient._token_exp = now + int(data.get("expires_in", 3000)) - 60
        return PayPalHttpClient._token

    async def _request(
        self, method: str, path: str, json: dict | None = None
    ) -> dict[str, Any]:
        token = await self._get_token()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.request(
                    method,
                    f"{self._base}{path}",
                    json=json,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            raise ProviderError("paypal", f"Error de red: {exc}") from exc
        if resp.status_code >= 400:
            raise ProviderError(
                "paypal", "Solicitud rechazada por PayPal", details=_safe_json(resp)
            )
        return resp.json() if resp.content else {}

    async def create_subscription(
        self, *, plan_id: str, user_id: str, email: str | None
    ) -> PayPalSubscription:
        body: dict[str, Any] = {
            "plan_id": plan_id,
            "custom_id": user_id,
            "application_context": {
                "brand_name": self._settings.paypal_brand_name,
                "user_action": "SUBSCRIBE_NOW",
                "return_url": self._settings.paypal_return_url,
                "cancel_url": self._settings.paypal_cancel_url,
            },
        }
        if email:
            body["subscriber"] = {"email_address": email}
        data = await self._request("POST", "/v1/billing/subscriptions", json=body)
        approval = next(
            (
                link["href"]
                for link in data.get("links", [])
                if link.get("rel") == "approve"
            ),
            None,
        )
        return PayPalSubscription(
            subscription_id=data["id"],
            status=data.get("status", "APPROVAL_PENDING"),
            approval_url=approval,
        )

    async def get_subscription(self, subscription_id: str) -> PayPalSubscription:
        data = await self._request(
            "GET", f"/v1/billing/subscriptions/{subscription_id}"
        )
        return PayPalSubscription(
            subscription_id=data["id"], status=data.get("status", "")
        )

    async def cancel_subscription(self, subscription_id: str, reason: str) -> None:
        await self._request(
            "POST",
            f"/v1/billing/subscriptions/{subscription_id}/cancel",
            json={"reason": reason},
        )

    async def verify_webhook(self, headers: dict, body: dict) -> bool:
        if not self._settings.paypal_webhook_id:
            # Sin webhook_id configurado no se puede verificar la firma.
            return False
        payload = {
            "transmission_id": headers.get("paypal-transmission-id"),
            "transmission_time": headers.get("paypal-transmission-time"),
            "cert_url": headers.get("paypal-cert-url"),
            "auth_algo": headers.get("paypal-auth-algo"),
            "transmission_sig": headers.get("paypal-transmission-sig"),
            "webhook_id": self._settings.paypal_webhook_id,
            "webhook_event": body,
        }
        data = await self._request(
            "POST", "/v1/notifications/verify-webhook-signature", json=payload
        )
        return data.get("verification_status") == "SUCCESS"


def _safe_json(resp: httpx.Response) -> dict:
    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text}
