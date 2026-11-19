"""Categorisation precedence (spec 5.7): user rule > merchant default > LLM > OTHER."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider import ProviderUnavailableError
from app.ai.providers.fake import FakeProvider
from app.matching.merchant_normalizer import MerchantMatch, MerchantNormalizer
from app.models.enums import CategoryKey
from app.repositories.merchants import MerchantRepository
from app.services.categorization_service import CategorizationService
from tests.conftest import create_user


async def setup(db_session: AsyncSession, provider: FakeProvider | None = None):  # noqa: ANN201
    user = await create_user(db_session)
    repository = MerchantRepository(db_session)
    provider = provider or FakeProvider()
    return (
        user,
        repository,
        MerchantNormalizer(repository),
        CategorizationService(repository, provider),
        provider,
    )


async def test_a_known_merchant_uses_its_default_and_never_asks_the_model(
    db_session: AsyncSession,
) -> None:
    user, _, normalizer, categorizer, provider = await setup(db_session)
    provider.add_category("OPET", CategoryKey.TECHNOLOGY)  # a wrong answer, waiting to be used
    match = await normalizer.resolve(user.id, "OPET ISTASYONU 4411")

    suggestion = await categorizer.categorize(user.id, match, merchant_text="OPET", item_names=[])

    assert (suggestion.key, suggestion.source) == (CategoryKey.FUEL, "MERCHANT_DEFAULT")
    assert provider.classify_calls == 0


async def test_the_users_rule_beats_the_merchants_default(db_session: AsyncSession) -> None:
    user, repository, normalizer, categorizer, provider = await setup(db_session)
    match = await normalizer.resolve(user.id, "MIGROS")  # default GROCERY
    await repository.set_user_rule(user.id, match.merchant_id, CategoryKey.HOME)  # type: ignore[arg-type]

    suggestion = await categorizer.categorize(user.id, match, merchant_text="MIGROS", item_names=[])

    assert (suggestion.key, suggestion.source) == (CategoryKey.HOME, "USER_RULE")
    assert provider.classify_calls == 0


async def test_a_rule_can_be_changed_and_belongs_to_one_user(db_session: AsyncSession) -> None:
    user, repository, normalizer, categorizer, _ = await setup(db_session)
    other = await create_user(db_session, "other")
    match = await normalizer.resolve(user.id, "MIGROS")
    await repository.set_user_rule(user.id, match.merchant_id, CategoryKey.HOME)  # type: ignore[arg-type]
    await repository.set_user_rule(user.id, match.merchant_id, CategoryKey.FOOD_DRINK)  # type: ignore[arg-type]

    mine = await categorizer.categorize(user.id, match, merchant_text="MIGROS", item_names=[])
    theirs = await categorizer.categorize(other.id, match, merchant_text="MIGROS", item_names=[])

    assert (mine.key, mine.source) == (CategoryKey.FOOD_DRINK, "USER_RULE")
    assert (theirs.key, theirs.source) == (CategoryKey.GROCERY, "MERCHANT_DEFAULT")


async def test_an_unknown_merchant_is_classified_by_the_model(db_session: AsyncSession) -> None:
    user, _, normalizer, categorizer, provider = await setup(db_session)
    provider.add_category("Kose Manav", CategoryKey.GROCERY)
    match = await normalizer.resolve(user.id, "KOSE MANAV")
    assert match.kind == "NEW"

    suggestion = await categorizer.categorize(
        user.id, match, merchant_text="KOSE MANAV", item_names=["DOMATES"]
    )

    assert (suggestion.key, suggestion.source) == (CategoryKey.GROCERY, "LLM")
    assert provider.classify_calls == 1


async def test_a_model_failure_gives_other_not_an_error(db_session: AsyncSession) -> None:
    user, _, normalizer, categorizer, provider = await setup(db_session)
    match = await normalizer.resolve(user.id, "BILINMEYEN ISLETME")

    suggestion = await categorizer.categorize(
        user.id, match, merchant_text="BILINMEYEN ISLETME", item_names=[]
    )

    assert (suggestion.key, suggestion.source) == (CategoryKey.OTHER, "FALLBACK")
    assert provider.classify_calls == 1  # it was asked, and had no answer


async def test_a_provider_that_is_down_gives_other(db_session: AsyncSession) -> None:
    class Down(FakeProvider):
        def classify_category(self, merchant, items):  # type: ignore[no-untyped-def]
            raise ProviderUnavailableError("down")

    user, _, normalizer, categorizer, _ = await setup(db_session, Down())
    match = await normalizer.resolve(user.id, "BILINMEYEN ISLETME")

    suggestion = await categorizer.categorize(user.id, match, merchant_text="X", item_names=[])

    assert (suggestion.key, suggestion.source) == (CategoryKey.OTHER, "FALLBACK")


async def test_a_marketplace_default_of_other_asks_the_model_when_there_are_items(
    db_session: AsyncSession,
) -> None:
    user, _, normalizer, categorizer, provider = await setup(db_session)
    provider.add_category("Trendyol", CategoryKey.CLOTHING)
    match = await normalizer.resolve(user.id, "TRENDYOL.COM")
    assert match.default_category == CategoryKey.OTHER

    with_items = await categorizer.categorize(
        user.id, match, merchant_text="TRENDYOL", item_names=["TISORT"]
    )
    without_items = await categorizer.categorize(
        user.id, match, merchant_text="TRENDYOL", item_names=[]
    )

    assert (with_items.key, with_items.source) == (CategoryKey.CLOTHING, "LLM")
    assert (without_items.key, without_items.source) == (CategoryKey.OTHER, "MERCHANT_DEFAULT")
    assert provider.classify_calls == 1


async def test_a_users_rule_wins_even_for_a_marketplace(db_session: AsyncSession) -> None:
    user, repository, normalizer, categorizer, provider = await setup(db_session)
    match = await normalizer.resolve(user.id, "TRENDYOL")
    await repository.set_user_rule(user.id, match.merchant_id, CategoryKey.CLOTHING)  # type: ignore[arg-type]

    suggestion = await categorizer.categorize(
        user.id, match, merchant_text="TRENDYOL", item_names=["X"]
    )

    assert (suggestion.key, suggestion.source) == (CategoryKey.CLOTHING, "USER_RULE")
    assert provider.classify_calls == 0


async def test_without_consent_the_model_is_never_asked(db_session: AsyncSession) -> None:
    user, _, normalizer, categorizer, provider = await setup(db_session)
    provider.add_category("Kose Manav", CategoryKey.GROCERY)
    match = await normalizer.resolve(user.id, "KOSE MANAV")

    suggestion = await categorizer.categorize(
        user.id, match, merchant_text="KOSE MANAV", item_names=["DOMATES"], allow_ai=False
    )

    assert (suggestion.key, suggestion.source) == (CategoryKey.OTHER, "FALLBACK")
    assert provider.classify_calls == 0


async def test_nothing_to_go_on_means_other_without_a_model_call(db_session: AsyncSession) -> None:
    user, _, _, categorizer, provider = await setup(db_session)

    suggestion = await categorizer.categorize(
        user.id, MerchantMatch(kind="NONE"), merchant_text=None, item_names=[]
    )

    assert (suggestion.key, suggestion.source) == (CategoryKey.OTHER, "FALLBACK")
    assert provider.classify_calls == 0


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("MIGROS", CategoryKey.GROCERY),
        ("STARBUCKS COFFEE", CategoryKey.FOOD_DRINK),
        ("SHELL&TURCAS", CategoryKey.FUEL),
        ("NETFLIX.COM", CategoryKey.SUBSCRIPTION),
        ("TURKCELL ILETISIM HIZMETLERI", CategoryKey.BILLS),
        ("TEKNOSA IC VE DIS TICARET AS", CategoryKey.TECHNOLOGY),
        ("IKEA ISTANBUL", CategoryKey.HOME),
        ("GRATIS IC VE DIS TICARET A.S.", CategoryKey.HEALTH_CARE),
        ("LC WAIKIKI MAGAZACILIK HIZMETLERI TIC AS", CategoryKey.CLOTHING),
    ],
)
async def test_seeded_merchants_get_their_seeded_category(
    raw: str, expected: CategoryKey, db_session: AsyncSession
) -> None:
    user, _, normalizer, categorizer, provider = await setup(db_session)
    match = await normalizer.resolve(user.id, raw)

    suggestion = await categorizer.categorize(user.id, match, merchant_text=raw, item_names=[])

    assert (suggestion.key, suggestion.source) == (expected, "MERCHANT_DEFAULT")
    assert provider.classify_calls == 0
