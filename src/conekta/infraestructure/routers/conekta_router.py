"""Endpoints HTTP del módulo Conekta."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field

from src.conekta.application.conekta_service import ConektaService
from src.conekta.infraestructure.dependencies.container import get_conekta_service
from src.oauth.domain.authenticated_user import AuthenticatedUser
from src.oauth.infraestructure.dependencies.auth import get_current_user
from src.shared.schemas import CheckoutOut, SubscriptionOut

router = APIRouter(prefix="/conekta", tags=["conekta"])


class SubscribeRequest(BaseModel):
    plan_key: str = Field(..., examples=["vision-price-pro"])
    card_token: str = Field(
        ..., description="Token de tarjeta generado por Conekta.js en el frontend."
    )


class CreateCheckoutRequest(BaseModel):
    plan_key: str = Field(..., examples=["vision-price-pro"])
    allowed_payment_methods: list[str] | None = Field(
        default=None,
        description=(
            "Subconjunto de ['card','cash','bank_transfer'] a mostrar en el "
            "checkout. cash=OXXO, bank_transfer=SPEI. Si se omite, se usan "
            "los tres."
        ),
        examples=[["cash", "bank_transfer"]],
    )


@router.post(
    "/subscriptions",
    response_model=SubscriptionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_subscription(
    body: SubscribeRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ConektaService = Depends(get_conekta_service),
) -> SubscriptionOut:
    sub = await service.subscribe(user, body.plan_key, body.card_token)
    return SubscriptionOut.of(sub)


@router.post("/subscriptions/cancel", response_model=SubscriptionOut)
async def cancel_subscription(
    user: AuthenticatedUser = Depends(get_current_user),
    service: ConektaService = Depends(get_conekta_service),
) -> SubscriptionOut:
    sub = await service.cancel(user)
    return SubscriptionOut.of(sub)


@router.post(
    "/checkout",
    response_model=CheckoutOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_checkout(
    body: CreateCheckoutRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ConektaService = Depends(get_conekta_service),
) -> CheckoutOut:
    """Crea un link de pago (Conekta Checkout hospedado).

    El usuario paga en `checkout_url` con tarjeta, OXXO (efectivo) o SPEI
    (transferencia), según `allowed_payment_methods`. El pago se confirma
    vía `/conekta/webhook` (evento `order.paid`), que otorga la vigencia
    del plan automáticamente — no hace falta consultar este endpoint para
    activar nada, solo para mostrarle al usuario el estado.
    """
    order = await service.create_checkout(
        user, body.plan_key, body.allowed_payment_methods
    )
    return CheckoutOut.of(order)


@router.get("/checkout/{checkout_db_id}", response_model=CheckoutOut)
async def get_checkout(
    checkout_db_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ConektaService = Depends(get_conekta_service),
) -> CheckoutOut:
    order = await service.get_checkout(user, checkout_db_id)
    return CheckoutOut.of(order)


@router.delete("/payment-method", status_code=status.HTTP_200_OK)
async def remove_payment_method(
    user: AuthenticatedUser = Depends(get_current_user),
    service: ConektaService = Depends(get_conekta_service),
) -> dict:
    await service.remove_card(user)
    return {"detached": True}


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def conekta_webhook(
    request: Request,
    service: ConektaService = Depends(get_conekta_service),
) -> dict:
    event = await request.json()
    await service.handle_webhook(event)
    return {"received": True}
