"""Merchants, aliases and the per-user category rules.

`merchants` and global aliases are shared reference data (no owner). User aliases and rules
belong to one user: every function here that can return or write them takes `user_id`, and an
alias lookup can only ever see the global aliases and that user's own.
"""

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category, Merchant, MerchantAlias, UserCategoryRule
from app.models.enums import CategoryKey


@dataclass(frozen=True)
class MerchantInfo:
    id: uuid.UUID
    canonical_name: str
    default_category: CategoryKey | None


@dataclass(frozen=True)
class AliasHit:
    alias_normalized: str
    is_user_alias: bool
    merchant: MerchantInfo


class MerchantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_aliases(self, user_id: uuid.UUID, keys: Sequence[str]) -> list[AliasHit]:
        """Aliases equal to one of `keys`: the global ones and `user_id`'s own, nobody else's."""
        _require_uuid(user_id)
        if not keys:
            return []
        statement = (
            select(
                MerchantAlias.alias_normalized,
                MerchantAlias.user_id,
                Merchant.id,
                Merchant.canonical_name,
                Category.key,
            )
            .join(Merchant, Merchant.id == MerchantAlias.merchant_id)
            .outerjoin(Category, Category.id == Merchant.default_category_id)
            .where(
                MerchantAlias.alias_normalized.in_(list(keys)),
                or_(MerchantAlias.user_id.is_(None), MerchantAlias.user_id == user_id),
            )
        )
        rows = (await self._session.execute(statement)).all()
        return [
            AliasHit(
                alias_normalized=alias,
                is_user_alias=owner is not None,
                merchant=MerchantInfo(merchant_id, name, category),
            )
            for alias, owner, merchant_id, name, category in rows
        ]

    async def list_merchants(self, user_id: uuid.UUID) -> list[MerchantInfo]:
        """The merchants this user may be matched with, for fuzzy matching: the ones that have a
        global alias (the shared reference list) or one of this user's own aliases. A merchant
        that only another user named is not visible, so one user's private shop name can never
        be suggested to somebody else."""
        _require_uuid(user_id)
        visible = (
            select(MerchantAlias.id)
            .where(
                MerchantAlias.merchant_id == Merchant.id,
                or_(MerchantAlias.user_id.is_(None), MerchantAlias.user_id == user_id),
            )
            .exists()
        )
        statement = (
            select(Merchant.id, Merchant.canonical_name, Category.key)
            .outerjoin(Category, Category.id == Merchant.default_category_id)
            .where(visible)
            .order_by(Merchant.canonical_name)
        )
        return [MerchantInfo(*row) for row in (await self._session.execute(statement)).all()]

    async def get(self, merchant_id: uuid.UUID) -> MerchantInfo | None:
        statement = (
            select(Merchant.id, Merchant.canonical_name, Category.key)
            .outerjoin(Category, Category.id == Merchant.default_category_id)
            .where(Merchant.id == merchant_id)
        )
        row = (await self._session.execute(statement)).one_or_none()
        return MerchantInfo(*row) if row else None

    async def create(
        self,
        canonical_name: str,
        *,
        default_category: CategoryKey | None,
        alias_keys: Iterable[str],
        alias_user_id: uuid.UUID | None,
    ) -> MerchantInfo:
        """Spec 5.6 step 5: a new merchant with its aliases. Called when the user confirms a
        purchase (P07), never while a receipt is only being read. `alias_user_id` None makes the
        aliases global; a user id keeps them private to that user. An existing merchant with the
        same canonical name is returned unchanged (names are unique)."""
        existing = (
            await self._session.execute(
                select(Merchant.id).where(Merchant.canonical_name == canonical_name)
            )
        ).scalar_one_or_none()
        if existing is not None:
            merchant_id = existing
        else:
            category_id = (
                await self.category_id(default_category) if default_category is not None else None
            )
            merchant = Merchant(canonical_name=canonical_name, default_category_id=category_id)
            self._session.add(merchant)
            await self._session.flush()
            merchant_id = merchant.id

        for key in dict.fromkeys(alias_keys):
            statement = (
                pg_insert(MerchantAlias)
                .values(merchant_id=merchant_id, alias_normalized=key, user_id=alias_user_id)
                .on_conflict_do_nothing()
            )
            await self._session.execute(statement)
        await self._session.flush()
        info = await self.get(merchant_id)
        assert info is not None
        return info

    async def add_user_alias(
        self, user_id: uuid.UUID, merchant_id: uuid.UUID, alias_keys: Iterable[str]
    ) -> None:
        """Teach the app that these spellings mean this merchant for THIS user only."""
        _require_uuid(user_id)
        for key in dict.fromkeys(alias_keys):
            statement = (
                pg_insert(MerchantAlias)
                .values(merchant_id=merchant_id, alias_normalized=key, user_id=user_id)
                .on_conflict_do_nothing()
            )
            await self._session.execute(statement)
        await self._session.flush()

    async def category_id(self, key: CategoryKey) -> uuid.UUID:
        return (
            await self._session.execute(select(Category.id).where(Category.key == key))
        ).scalar_one()

    async def user_rule_category(
        self, user_id: uuid.UUID, merchant_id: uuid.UUID
    ) -> CategoryKey | None:
        """The category this user always wants for this merchant (spec 5.7, step 1)."""
        _require_uuid(user_id)
        statement = (
            select(Category.key)
            .join(UserCategoryRule, UserCategoryRule.category_id == Category.id)
            .where(UserCategoryRule.user_id == user_id, UserCategoryRule.merchant_id == merchant_id)
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def set_user_rule(
        self, user_id: uuid.UUID, merchant_id: uuid.UUID, category: CategoryKey
    ) -> None:
        """Store or change the user's rule. (The app UI for it is P07; tests use it now.)"""
        _require_uuid(user_id)
        category_id = await self.category_id(category)
        statement = (
            pg_insert(UserCategoryRule)
            .values(user_id=user_id, merchant_id=merchant_id, category_id=category_id)
            .on_conflict_do_update(
                index_elements=["user_id", "merchant_id"], set_={"category_id": category_id}
            )
        )
        await self._session.execute(statement)
        await self._session.flush()


def _require_uuid(user_id: object) -> None:
    if not isinstance(user_id, uuid.UUID):
        raise TypeError("user_id must be a uuid.UUID")
