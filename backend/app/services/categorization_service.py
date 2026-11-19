"""Hybrid categorisation, spec 5.7.

Order, first hit wins:
  1. the user's own rule for this merchant        (USER_RULE)
  2. the merchant's default category              (MERCHANT_DEFAULT)
  3. the AI provider, constrained to the 13 keys  (LLM)
  4. OTHER when nothing else worked               (FALLBACK)

A merchant whose default is OTHER (marketplaces such as Trendyol) counts as "category unknown":
the items, when there are any, are shown to the LLM (DECISIONS). The AI is only asked when the
caller says it may (`allow_ai`: the user consented), and an AI failure is never an error: the
suggestion is OTHER. The user can always change the category in the review screen (P07).
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import Literal

from app.ai.provider import AIProvider, ProviderError
from app.matching.merchant_normalizer import MerchantMatch
from app.models.enums import CategoryKey
from app.repositories.merchants import MerchantRepository

logger = logging.getLogger("receiptbox.categorization")

CategorySource = Literal["USER_RULE", "MERCHANT_DEFAULT", "LLM", "FALLBACK"]


@dataclass(frozen=True)
class CategorySuggestion:
    key: CategoryKey
    source: CategorySource


class CategorizationService:
    def __init__(self, repository: MerchantRepository, provider: AIProvider) -> None:
        self._repository = repository
        self._provider = provider

    async def categorize(
        self,
        user_id: uuid.UUID,
        match: MerchantMatch,
        *,
        merchant_text: str | None,
        item_names: list[str],
        allow_ai: bool = True,
    ) -> CategorySuggestion:
        if match.merchant_id is not None:
            rule = await self._repository.user_rule_category(user_id, match.merchant_id)
            if rule is not None:
                return CategorySuggestion(rule, "USER_RULE")
            default = match.default_category
            if default is not None and default != CategoryKey.OTHER:
                return CategorySuggestion(default, "MERCHANT_DEFAULT")
            if default == CategoryKey.OTHER and not item_names:
                return CategorySuggestion(CategoryKey.OTHER, "MERCHANT_DEFAULT")

        # A known merchant is asked by its canonical name; an unknown one by what the receipt
        # printed (more informative than our cleaned-up guess).
        name = (
            match.canonical_name
            if match.merchant_id is not None
            else (merchant_text or match.canonical_name or "").strip()
        )
        if not allow_ai or not (name or item_names):
            return CategorySuggestion(CategoryKey.OTHER, "FALLBACK")
        return await self._ask_the_model(name, item_names)

    async def _ask_the_model(self, merchant: str, item_names: list[str]) -> CategorySuggestion:
        try:
            key = await asyncio.to_thread(self._provider.classify_category, merchant, item_names)
        except (ProviderError, NotImplementedError) as error:
            logger.warning("classification_failed", extra={"error_type": type(error).__name__})
            return CategorySuggestion(CategoryKey.OTHER, "FALLBACK")
        return CategorySuggestion(key, "LLM")
