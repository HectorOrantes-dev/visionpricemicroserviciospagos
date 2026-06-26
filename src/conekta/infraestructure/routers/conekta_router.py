"""Endpoints HTTP del módulo Conekta."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field

from src.conekta.application.conekta_service import ConektaService
from src.conekta.infraestructure.dependencies.container import get_conekta_service
from src.oauth.domain.authenticated_user import AuthenticatedUser
from src.oauth.infraestructure.dependencies.auth import get_current_user
from src.shared.schemas import SubscriptionOut

router = APIRouter(prefix="/conekta", tags=["conekta"])


class SubscribeRequest(BaseModel):
    plan_key: str = Field(..., examples=["vision-price-pro"])
    card_token: str = Field(
        ..., description="Token de tarjeta generado por Conekta.js en el frontend."
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
