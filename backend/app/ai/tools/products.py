"""Product tools: products, one product's card and documents (spec 13.2). They reuse the P12
`ProductService` (warranty, return window, financing cost, documents) and the P07
`DocumentService`. Another user's id gives exactly what an unknown id gives: nothing."""

import uuid
from datetime import date
from typing import Any

from pydantic import Field, model_validator

from app.ai.tools.base import (
    CATEGORY_LABELS,
    Action,
    Output,
    Tool,
    ToolArgs,
    ToolArgumentError,
    ToolContext,
    day_tr,
    tl,
)
from app.core.errors import NotFoundError
from app.core.text import normalize_alias_key
from app.models import Document
from app.models.enums import CategoryKey, DocumentType, ProductStatus, WarrantySource
from app.schemas.documents import DocumentOut
from app.schemas.products import ProductOut
from app.services.document_service import DocumentService
from app.services.product_service import ProductService

MAX_PRODUCTS = 20
MAX_DOCUMENT_ACTIONS = 3
MAX_PRODUCT_ACTIONS = 3

STATUS_TR = {
    ProductStatus.ACTIVE: "kullanımda",
    ProductStatus.RETURNED: "iade edildi",
    ProductStatus.ARCHIVED: "arşivde",
}
WARRANTY_SOURCE_TR = {
    WarrantySource.DOCUMENT: "belgeden",
    WarrantySource.LEGAL_DEFAULT: "yasal varsayılan",
    WarrantySource.USER: "kullanıcı girdi",
}
DOCUMENT_TYPE_TR = {
    DocumentType.RECEIPT_IMAGE: "fiş görüntüsü",
    DocumentType.INVOICE: "fatura",
    DocumentType.WARRANTY: "garanti belgesi",
    DocumentType.OTHER: "belge",
}


def _product_service(ctx: ToolContext) -> ProductService:
    return ProductService(ctx.session, ctx.settings, today=lambda: ctx.today)


def _product(p: ProductOut) -> dict[str, Any]:
    out: dict[str, Any] = {
        "product_id": str(p.id),
        "name": p.name,
        "brand": p.brand,
        "model": p.model,
        "category": CATEGORY_LABELS[p.category_key] if p.category_key else None,
        "merchant": p.merchant_display,
        "purchase_date": p.purchase_date.isoformat() if p.purchase_date else None,
        "price": tl(p.purchase_price_minor) if p.purchase_price_minor is not None else None,
        "status": STATUS_TR[p.status],
        "document_count": p.document_count,
    }
    if p.warranty is not None:
        out["warranty"] = {
            "end_date": p.warranty.end_date.isoformat(),
            "days_left": p.warranty.days_left,
            "source": WARRANTY_SOURCE_TR[p.warranty.source],
            "confirmed": p.warranty.confirmed,
        }
    if p.return_window is not None:
        out["return_window"] = {
            "end_date": p.return_window.end_date.isoformat(),
            "days_left": p.return_window.days_left,
            "status": p.return_window.status.value,
        }
    return out


def _document(d: DocumentOut | Document) -> dict[str, Any]:
    return {
        "document_id": str(d.id),
        "type": DOCUMENT_TYPE_TR[DocumentType(d.type)],
        "file": "PDF" if d.mime_type == "application/pdf" else "görüntü",
        "added": d.created_at.date().isoformat(),
    }


def _document_actions(output: Output) -> list[Action]:
    return [
        Action(
            "OPEN_DOCUMENT",
            f"{doc['type'].capitalize()} aç",
            {"id": doc["document_id"], "pdf": "true" if doc["file"] == "PDF" else "false"},
        )
        for doc in (output.get("documents") or [])[:MAX_DOCUMENT_ACTIONS]
    ]


# ---- search_products -----------------------------------------------------------------------------


class SearchProductsArgs(ToolArgs):
    query: str | None = Field(
        default=None,
        max_length=60,
        description="Words of the product name, brand, model or shop. Leave empty to list all.",
    )
    category: CategoryKey | None = Field(default=None, description="Only this category.")
    status: ProductStatus | None = Field(
        default=None, description="ACTIVE (in use), RETURNED or ARCHIVED. Empty: all."
    )


def _matches(query: str, p: ProductOut) -> bool:
    words = normalize_alias_key(query).split()
    haystack = normalize_alias_key(
        " ".join(x for x in (p.name, p.brand, p.model, p.merchant_display) if x)
    )
    return all(word in haystack for word in words)


async def _search_products(ctx: ToolContext, args: SearchProductsArgs) -> Output:
    found = await _product_service(ctx).products(
        ctx.user_id, statuses=[args.status] if args.status else None
    )
    items = [
        p
        for p in found.items
        if (args.category is None or p.category_key == args.category)
        and (not args.query or _matches(args.query, p))
    ]
    return {
        "count": len(items),
        "products": [_product(p) for p in items[:MAX_PRODUCTS]],
    }


def _search_actions(args: SearchProductsArgs, output: Output) -> list[Action]:
    return [
        Action("OPEN_PRODUCT", f"{p['name']} kartı", {"id": p["product_id"]})
        for p in (output.get("products") or [])[:MAX_PRODUCT_ACTIONS]
    ]


def _search_summary(args: SearchProductsArgs, output: Output) -> str:
    products = output.get("products") or []
    if not products:
        return "Kayıtlarında bununla ilgili bir ürün bulamadım."
    lines = [f"Bulduğum {output['count']} ürün:"]
    for p in products[:5]:
        line = f"- {p['name']}"
        if p.get("warranty"):
            line += f", garanti bitişi {day_tr(date.fromisoformat(p['warranty']['end_date']))}"
        lines.append(line)
    return "\n".join(lines)


SEARCH_PRODUCTS = Tool(
    name="search_products",
    description=(
        "Finds the user's tracked products (with warranty and return window) by words of the "
        "name, brand, model or shop, by category or status. With no query it lists all products."
    ),
    args_model=SearchProductsArgs,
    run=_search_products,
    actions=_search_actions,
    summary=_search_summary,
)


# ---- get_product_details -----------------------------------------------------------------------


class ProductDetailsArgs(ToolArgs):
    product_id: uuid.UUID = Field(description="A product_id from search_products.")


async def _product_details(ctx: ToolContext, args: ProductDetailsArgs) -> Output:
    try:
        detail = await _product_service(ctx).detail(ctx.user_id, args.product_id)
    except NotFoundError:
        return {"found": False}
    out: Output = {"found": True, **_product(detail)}
    if detail.financing_cost_minor is not None:
        out["installment_financing_cost"] = tl(detail.financing_cost_minor)
    if detail.refundable_minor is not None:
        out["still_refundable"] = tl(detail.refundable_minor)
    out["documents"] = [_document(d) for d in detail.documents]
    return out


def _details_actions(args: ProductDetailsArgs, output: Output) -> list[Action]:
    if not output.get("found"):
        return []
    return [Action("OPEN_PRODUCT", f"{output['name']} kartı", {"id": output["product_id"]})]


def _details_summary(args: ProductDetailsArgs, output: Output) -> str:
    if not output.get("found"):
        return "Kayıtlarında bu ürünü bulamadım."
    parts = [f"{output['name']}"]
    if output.get("price"):
        parts.append(f"fiyatı {output['price']}")
    warranty = output.get("warranty")
    if warranty:
        parts.append(
            f"garantisi {day_tr(date.fromisoformat(warranty['end_date']))} tarihinde bitiyor "
            f"({warranty['days_left']} gün kaldı)"
        )
    return ", ".join(parts) + "."


GET_PRODUCT_DETAILS = Tool(
    name="get_product_details",
    description=(
        "One product's card: price, shop, warranty end and days left, return window, the "
        "documents (receipt, invoice, warranty card), the installment financing cost."
    ),
    args_model=ProductDetailsArgs,
    run=_product_details,
    actions=_details_actions,
    summary=_details_summary,
)


# ---- find_documents ----------------------------------------------------------------------------


class FindDocumentsArgs(ToolArgs):
    transaction_id: uuid.UUID | None = Field(
        default=None, description="A transaction_id from query_transactions."
    )
    product_id: uuid.UUID | None = Field(
        default=None, description="A product_id from search_products."
    )

    @model_validator(mode="after")
    def _exactly_one(self) -> "FindDocumentsArgs":
        if (self.transaction_id is None) == (self.product_id is None):
            raise ValueError("Send exactly one of transaction_id or product_id.")
        return self


async def _find_documents(ctx: ToolContext, args: FindDocumentsArgs) -> Output:
    if args.product_id is not None:
        try:
            detail = await _product_service(ctx).detail(ctx.user_id, args.product_id)
        except NotFoundError:
            return {"found": False, "count": 0, "documents": []}
        documents = [_document(d) for d in detail.documents]
        return {
            "found": True,
            "product": detail.name,
            "count": len(documents),
            "documents": documents,
        }
    if args.transaction_id is None:  # pragma: no cover - the validator guarantees one
        raise ToolArgumentError("Send exactly one of transaction_id or product_id.")
    service = DocumentService(ctx.session, ctx.storage, ctx.settings)
    rows = await service.list_for_transaction(ctx.user_id, args.transaction_id)
    documents = [_document(d) for d in rows]
    return {"found": bool(documents), "count": len(documents), "documents": documents}


def _documents_actions(args: FindDocumentsArgs, output: Output) -> list[Action]:
    return _document_actions(output)


def _documents_summary(args: FindDocumentsArgs, output: Output) -> str:
    documents = output.get("documents") or []
    if not documents:
        return "Bunun için kayıtlı bir belge bulamadım."
    kinds = ", ".join(sorted({d["type"] for d in documents}))
    return f"{len(documents)} belge buldum ({kinds}). Aşağıdaki düğmeyle açabilirsin."


FIND_DOCUMENTS = Tool(
    name="find_documents",
    description=(
        "The stored files (receipt image, invoice, warranty card) of one purchase or one product."
    ),
    args_model=FindDocumentsArgs,
    run=_find_documents,
    actions=_documents_actions,
    summary=_documents_summary,
)
