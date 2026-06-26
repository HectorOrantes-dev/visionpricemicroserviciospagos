"""Catálogo de planes — fuente única de verdad.

Mapea el `plan_key` lógico (usado por el frontend de VisionPrice) a los IDs reales
de plan en cada proveedor (Conekta / PayPal) y su precio. Los IDs concretos viven
en variables de entorno para no acoplar código a un ambiente test/prod.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.shared.config import Settings, get_settings


class Provider(str, Enum):
    CONEKTA = "conekta"
    PAYPAL = "paypal"


@dataclass(frozen=True)
class Plan:
    plan_key: str
    name: str
    price_mxn: int
    currency: str
    interval: str  # "month"
    description: str
    conekta_plan_id: str
    paypal_plan_id: str

    def provider_plan_id(self, provider: Provider) -> str:
        return (
            self.conekta_plan_id
            if provider == Provider.CONEKTA
            else self.paypal_plan_id
        )


def build_catalog(settings: Settings) -> dict[str, Plan]:
    return {
        "vision-price-pro": Plan(
            plan_key="vision-price-pro",
            name="Pro",
            price_mxn=349,
            currency="MXN",
            interval="month",
            description="Suscripción Pro de Vision Price",
            conekta_plan_id=settings.conekta_plan_pro,
            paypal_plan_id=settings.paypal_plan_pro,
        ),
        "vision-price-plan": Plan(
            plan_key="vision-price-plan",
            name="Plan",
            price_mxn=899,
            currency="MXN",
            interval="month",
            description="Suscripción Plan de Vision Price",
            conekta_plan_id=settings.conekta_plan_equipos,
            paypal_plan_id=settings.paypal_plan_equipos,
        ),
    }


def get_plan(plan_key: str, settings: Settings | None = None) -> Plan:
    settings = settings or get_settings()
    catalog = build_catalog(settings)
    plan = catalog.get(plan_key)
    if plan is None:
        from src.shared.errors import PlanNotFoundError

        raise PlanNotFoundError(plan_key)
    return plan
