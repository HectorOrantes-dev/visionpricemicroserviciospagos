"""Endpoints HTTP del módulo PayPal."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field

from src.oauth.domain.authenticated_user import AuthenticatedUser
from src.oauth.infraestructure.dependencies.auth import get_current_user
from src.paypal.application.paypal_service import PayPalService
from src.paypal.infraestructure.dependencies.container import get_paypal_service
from src.shared.schemas import SubscriptionOut

router = APIRouter(prefix="/paypal", tags=["paypal"])


class SubscribeRequest(BaseModel):
    plan_key: str = Field(..., examples=["vision-price-pro"])


class PayPalSubscribeResponse(BaseModel):
    subscription: SubscriptionOut
    approval_url: str | None = Field(
        None, description="URL a la que se debe redirigir al usuario para aprobar."
    )


@router.post(
    "/subscriptions",
    response_model=PayPalSubscribeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_subscription(
    body: SubscribeRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    service: PayPalService = Depends(get_paypal_service),
) -> PayPalSubscribeResponse:
    result = await service.create_subscription(user, body.plan_key)
    return PayPalSubscribeResponse(
        subscription=SubscriptionOut.of(result.subscription),
        approval_url=result.approval_url,
    )


@router.post("/subscriptions/{subscription_id}/cancel", response_model=SubscriptionOut)
async def cancel_subscription(
    subscription_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: PayPalService = Depends(get_paypal_service),
) -> SubscriptionOut:
    sub = await service.cancel(user, subscription_id)
    return SubscriptionOut.of(sub)


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def paypal_webhook(
    request: Request,
    service: PayPalService = Depends(get_paypal_service),
) -> dict:
    body = await request.json()
    headers = {k.lower(): v for k, v in request.headers.items()}
    await service.handle_webhook(headers, body)
    return {"received": True}
