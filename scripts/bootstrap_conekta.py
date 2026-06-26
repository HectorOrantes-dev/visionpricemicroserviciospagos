"""Verifica/crea los planes de suscripción en Conekta para Vision Price.

Crea (si no existen) los planes:
  - planes-app-pro     -> 349 MXN/mes
  - planes-app-equipo  -> 899 MXN/mes

Conekta maneja montos en centavos. Los IDs deben coincidir con CONEKTA_PLAN_PRO
y CONEKTA_PLAN_EQUIPOS del .env.

Uso:
    python -m scripts.bootstrap_conekta
"""
from __future__ import annotations

import sys

import httpx

from src.shared.config import get_settings

PLANS = [
    {"id_env": "conekta_plan_pro", "name": "Vision Price Pro", "amount": 349_00},
    {"id_env": "conekta_plan_equipos", "name": "Vision Price Plan", "amount": 899_00},
]


def _client(settings) -> httpx.Client:
    return httpx.Client(
        base_url=settings.conekta_api_base,
        auth=httpx.BasicAuth(settings.conekta_private_key, ""),
        headers={
            "Accept": f"application/vnd.conekta-v{settings.conekta_api_version}+json",
            "Content-Type": "application/json",
        },
        timeout=30.0,
    )


def main() -> int:
    settings = get_settings()
    if not settings.conekta_private_key:
        print("ERROR: falta CONEKTA_PRIVATE_KEY en .env")
        return 1

    env = "PRODUCCIÓN" if settings.conekta_private_key.startswith("key_live") else "TEST"
    print(f"Conekta ambiente: {env}\n")

    with _client(settings) as client:
        for spec in PLANS:
            plan_id = getattr(settings, spec["id_env"])
            if not plan_id:
                print(f"(omitido) {spec['id_env']} vacío en .env")
                continue

            existing = client.get(f"/plans/{plan_id}")
            if existing.status_code == 200:
                amount = existing.json().get("amount")
                print(f"OK  {plan_id} ya existe (amount={amount})")
                continue

            resp = client.post(
                "/plans",
                json={
                    "id": plan_id,
                    "name": spec["name"],
                    "amount": spec["amount"],
                    "currency": "MXN",
                    "interval": "month",
                    "frequency": 1,
                    "expiry_count": 0,
                },
            )
            if resp.status_code >= 400:
                print(f"ERROR creando {plan_id}: {resp.status_code} {resp.text}")
            else:
                print(f"CREADO  {plan_id} ({spec['amount'] // 100} MXN)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
