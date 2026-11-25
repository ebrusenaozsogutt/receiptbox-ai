"""Products, warranties, return windows and refunds (spec 9, 10, 16, P12). No logic here: see
services/product_service.py and services/refund_service.py (through TransactionService)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentUser, ProductServiceDep, TransactionServiceDep
from app.models.enums import ProductStatus
from app.schemas.errors import ErrorResponse
from app.schemas.products import (
    DismissIn,
    ProductDetail,
    ProductIn,
    ProductList,
    ProductPatch,
    ProductSuggestionList,
    RefundIn,
    RefundLinkIn,
    RefundSuggestionList,
    ReturnWindowIn,
    WarrantyIn,
)
from app.schemas.transactions import TransactionDetail

router = APIRouter(tags=["products"])

_UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "AUTH_INVALID_TOKEN or AUTH_EXPIRED"}}
_NOT_FOUND = {404: {"model": ErrorResponse, "description": "NOT_FOUND (also for another user's)"}}
_INVALID = {422: {"model": ErrorResponse, "description": "VALIDATION_ERROR"}}


@router.get("/products", response_model=ProductList, responses=_UNAUTHORIZED)
async def list_products(
    user: CurrentUser,
    service: ProductServiceDep,
    status_: Annotated[list[ProductStatus] | None, Query(alias="status")] = None,
) -> ProductList:
    """The user's products (filter with `status`, repeatable), newest purchase first, each with
    its warranty and return window (days left, source)."""
    return await service.products(user.id, status_)


@router.post(
    "/products",
    response_model=ProductDetail,
    status_code=status.HTTP_201_CREATED,
    responses={**_UNAUTHORIZED, **_NOT_FOUND, **_INVALID},
)
async def create_product(
    body: ProductIn, user: CurrentUser, service: ProductServiceDep
) -> ProductDetail:
    """From a purchase, a line of its receipt, or by hand. Proposes a 2-year warranty
    (LEGAL_DEFAULT, unconfirmed) and, for an online purchase, a 14-day return window
    (LEGAL_DEFAULT). In-store: no return window until the user enters the store's."""
    return await service.create(user.id, body)


@router.get(
    "/products/suggestions",
    response_model=ProductSuggestionList,
    responses=_UNAUTHORIZED,
)
async def product_suggestions(
    user: CurrentUser, service: ProductServiceDep
) -> ProductSuggestionList:
    """Purchases or receipt lines worth tracking (spec 10.1), not yet products, not dismissed."""
    return await service.suggestions(user.id)


@router.post(
    "/products/suggestions/dismiss",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**_UNAUTHORIZED, **_NOT_FOUND},
)
async def dismiss_suggestion(
    body: DismissIn, user: CurrentUser, service: ProductServiceDep
) -> Response:
    """ "Hayır, bir daha sorma": never suggest this purchase (or this receipt line) again."""
    await service.dismiss(user.id, body)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/products/{product_id}",
    response_model=ProductDetail,
    responses={**_UNAUTHORIZED, **_NOT_FOUND},
)
async def get_product(
    product_id: uuid.UUID, user: CurrentUser, service: ProductServiceDep
) -> ProductDetail:
    return await service.detail(user.id, product_id)


@router.patch(
    "/products/{product_id}",
    response_model=ProductDetail,
    responses={**_UNAUTHORIZED, **_NOT_FOUND, **_INVALID},
)
async def patch_product(
    product_id: uuid.UUID, body: ProductPatch, user: CurrentUser, service: ProductServiceDep
) -> ProductDetail:
    """Edit the fields, archive ("Arşivle"), or mark a product without a purchase RETURNED."""
    return await service.patch(user.id, product_id, body)


@router.delete(
    "/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**_UNAUTHORIZED, **_NOT_FOUND},
)
async def delete_product(
    product_id: uuid.UUID, user: CurrentUser, service: ProductServiceDep
) -> Response:
    await service.delete(user.id, product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/products/{product_id}/warranty",
    response_model=ProductDetail,
    responses={**_UNAUTHORIZED, **_NOT_FOUND, **_INVALID},
)
async def put_warranty(
    product_id: uuid.UUID, body: WarrantyIn, user: CurrentUser, service: ProductServiceDep
) -> ProductDetail:
    """Accept the default (same date, LEGAL_DEFAULT, confirmed) or enter another end (USER /
    DOCUMENT)."""
    return await service.put_warranty(user.id, product_id, body)


@router.put(
    "/products/{product_id}/return-window",
    response_model=ProductDetail,
    responses={**_UNAUTHORIZED, **_NOT_FOUND, **_INVALID},
)
async def put_return_window(
    product_id: uuid.UUID, body: ReturnWindowIn, user: CurrentUser, service: ProductServiceDep
) -> ProductDetail:
    """The store's return period (STORE_POLICY), the user's own date (USER), or the 14-day
    default of an online purchase (LEGAL_DEFAULT)."""
    return await service.put_return_window(user.id, product_id, body)


# ---- refunds ------------------------------------------------------------------------------------


@router.post(
    "/transactions/{transaction_id}/refund",
    response_model=TransactionDetail,
    responses={
        **_UNAUTHORIZED,
        **_NOT_FOUND,
        422: {"model": ErrorResponse, "description": "REFUND_TOO_LARGE or VALIDATION_ERROR"},
    },
)
async def refund_transaction(
    transaction_id: uuid.UUID, body: RefundIn, user: CurrentUser, service: TransactionServiceDep
) -> TransactionDetail:
    """ "İade edildi" (full or partial, at most what is left). Spending goes down in the
    purchase's own month; the returned product becomes RETURNED. Answers the purchase."""
    return await service.refund(user.id, transaction_id, body)


@router.get("/refunds/suggestions", response_model=RefundSuggestionList, responses=_UNAUTHORIZED)
async def refund_suggestions(
    user: CurrentUser, service: TransactionServiceDep
) -> RefundSuggestionList:
    """The bank CREDIT rows that wait, each with the purchases it may refund (same shop, amount at
    most what is left, at most 60 days after the purchase). Suggestions only."""
    return await service.refund_suggestions(user.id)


@router.post(
    "/observations/{observation_id}/link-refund",
    response_model=TransactionDetail,
    responses={
        **_UNAUTHORIZED,
        **_NOT_FOUND,
        409: {"model": ErrorResponse, "description": "OBSERVATION_NOT_PENDING"},
        422: {
            "model": ErrorResponse,
            "description": "NOT_A_REFUND_ROW, REFUND_TOO_LARGE or VALIDATION_ERROR",
        },
    },
)
async def link_refund(
    observation_id: uuid.UUID,
    body: RefundLinkIn,
    user: CurrentUser,
    service: TransactionServiceDep,
) -> TransactionDetail:
    """The user's answer to a suggestion: this bank CREDIT row is a refund of that purchase."""
    return await service.link_refund(user.id, observation_id, body)
