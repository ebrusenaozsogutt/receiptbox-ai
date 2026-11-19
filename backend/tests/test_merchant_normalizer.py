"""Merchant normalisation (spec 5.6): the cleaning functions, and name -> canonical merchant
against the seeded reference data (223 merchants, their global aliases)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.matching.merchant_normalizer import (
    MerchantNormalizer,
    clean_name,
    fold_ascii,
    fuzzy_pick,
    turkish_title,
    vkn_alias_key,
)
from app.models.enums import CategoryKey
from app.repositories.merchants import MerchantRepository
from tests.conftest import create_user

# ---- pure functions --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "stripped"),
    [
        ("MIGROS TICARET AS", "MIGROS"),
        ("Migros Ticaret A.Ş.", "MİGROS"),
        ("MİGROS SANAL MARKET", "MİGROS"),
        ("MIGROS MAGAZACILIK 1234 KONYA", "MIGROS"),
        ("MIGROS NO 12 KASA 3", "MIGROS"),
        ("SHELL&TURCAS", "SHELL TURCAS"),
        ("TRENDYOL.COM", "TRENDYOL"),
        ("Hepsiburada.com", "HEPSİBURADA"),
        ("AMAZON.COM.TR", "AMAZON"),
        ("SECOM", "SECOM"),
        ("A101 YENI MAGAZACILIK A.S.", "A101 YENI"),
        ("KOCTAS YAPI MARKETLERI SANAYI VE TICARET AS", "KOCTAS YAPI MARKETLERI"),
        ("LC WAIKIKI MAGAZACILIK HIZMETLERI TIC AS", "LC WAIKIKI"),
        ("OPET ISTASYONU 4411", "OPET"),
        ("ÖRNEK ELEKTRONİK TỈCARET A.Ş.", "ÖRNEK"),  # ML Kit read İ as Ỉ
        ("IKEA ISTANBUL", "IKEA"),
        ("ADANA KEBAP", "ADANA KEBAP"),  # a city name inside the name is not removed
        ("USTA KEBAP ADANA", "USTA KEBAP"),  # ... only at the end
        ("A. Ş.", "A Ş"),  # nothing but a legal form: keep something
        ("  ", ""),
    ],
)
def test_clean_name_steps_one_and_two(raw: str, stripped: str) -> None:
    assert clean_name(raw).stripped == stripped


def test_a_name_made_only_of_noise_is_kept_whole() -> None:
    assert clean_name("TICARET AS").stripped == "TICARET AS"
    assert clean_name("SANAL MARKET").stripped == "SANAL MARKET"


def test_alias_keys_cover_both_spellings_and_the_stripped_name() -> None:
    keys = clean_name("Migros Ticaret A.Ş.").lookup_keys

    assert keys == ["MİGROS TİCARET AŞ", "MIGROS TICARET AS", "MİGROS", "MIGROS"]


def test_turkish_casing_rules() -> None:
    assert clean_name("istanbul kebapçısı").full == "İSTANBUL KEBAPÇISI"
    assert clean_name("ışık market").full == "IŞIK MARKET"
    assert fold_ascii("ŞÖĞÜT İÇ") == "SOGUT IC"


@pytest.mark.parametrize(
    ("name", "title"),
    [
        ("KOSE MANAV", "Kose Manav"),
        ("İSTANBUL KEBAPÇISI", "İstanbul Kebapçısı"),
        ("A101 YENI", "A101 Yeni"),
        ("KFC", "KFC"),
        ("SIFA ECZANESI", "Sifa Eczanesi"),
    ],
)
def test_turkish_title(name: str, title: str) -> None:
    assert turkish_title(name) == title


def test_fuzzy_pick_needs_a_close_name_and_enough_letters() -> None:
    names = ["MIGROS", "KAHVE DUNYASI", "STARBUCKS", "HEPSIBURADA"]

    assert fuzzy_pick("MIGROSS", names)[0] == 0  # type: ignore[index]
    assert fuzzy_pick("STARBUCK", names)[0] == 2  # type: ignore[index]
    assert fuzzy_pick("HEPSIBURADAA", names)[0] == 3  # type: ignore[index]
    assert fuzzy_pick("KAHVE", names) is None  # a subset of "KAHVE DUNYASI" scores 100 ...
    assert fuzzy_pick("BIM", ["BIN"]) is None  # ... and very short names never match fuzzily
    assert fuzzy_pick("BAKKAL AHMET", names) is None
    assert fuzzy_pick("", names) is None
    assert fuzzy_pick("MIGROS", []) is None


# ---- name -> canonical merchant (seeded database) --------------------------------------------

# (what the receipt or statement says, canonical merchant in the seed)
VARIANTS = [
    ("MIGROS TICARET AS", "Migros"),
    ("MİGROS TİCARET AŞ", "Migros"),
    ("MİGROS SANAL MARKET", "Migros"),
    ("MIGROS MAGAZACILIK 1234 KONYA", "Migros"),
    ("Migros", "Migros"),
    ("5M MIGROS", "Migros"),
    ("A101 YENI MAGAZACILIK", "A101"),
    ("A 101", "A101"),
    ("BIM BIRLESIK MAGAZALAR A.S.", "BİM"),
    ("BİM BİRLEŞİK MAĞAZALAR AŞ", "BİM"),
    ("ŞOK MARKETLER TİCARET A.Ş.", "ŞOK"),
    ("SOK MARKET", "ŞOK"),
    ("CARREFOURSA ISTANBUL", "CarrefourSA"),
    ("SHELL&TURCAS", "Shell"),
    ("SHELL TURCAS PETROL AS", "Shell"),
    ("OPET ISTASYONU 4411", "Opet"),
    ("OPET PETROLCULUK AS", "Opet"),
    ("PETROL OFISI", "Petrol Ofisi"),
    ("TRENDYOL.COM", "Trendyol"),
    ("Hepsiburada.com", "Hepsiburada"),  # the ".com" is dropped, then it is an alias
    ("MIGROSS", "Migros"),  # a typo: found by fuzzy matching
    ("HEPSIBURADAA", "Hepsiburada"),
    ("STARBUCKS COFFEE", "Starbucks"),
    ("STARBUCKS COFFEE TURKIYE", "Starbucks"),
    ("STARBUCK", "Starbucks"),  # a typo
    ("McDonald's", "McDonald's"),
    ("H&M", "H&M"),
    ("LC WAIKIKI MAGAZACILIK HIZMETLERI TIC AS", "LC Waikiki"),
    ("GRATIS IC VE DIS TICARET A.S.", "Gratis"),
    ("TEKNOSA IC VE DIS TICARET AS", "Teknosa"),
    ("VATAN BILGISAYAR SANAYI VE TICARET AS", "Vatan Bilgisayar"),
    ("MEDIA MARKT TURKIYE TICARET", "MediaMarkt"),
    ("KOCTAS YAPI MARKETLERI", "Koçtaş"),
    ("IKEA ISTANBUL", "IKEA"),
    ("NETFLIX.COM", "Netflix"),
    ("SPOTIFY AB", "Spotify"),
    ("YEMEKSEPETI ELEKTRONIK", "Yemeksepeti"),
    ("GETIR PERAKENDE LOJISTIK", "Getir"),
    ("TURKCELL ILETISIM HIZMETLERI", "Turkcell"),
    ("PTT POSTA", "PTT"),
]


@pytest.mark.parametrize(("raw", "canonical"), VARIANTS)
async def test_real_looking_names_map_to_the_right_merchant(
    raw: str, canonical: str, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)

    match = await MerchantNormalizer(MerchantRepository(db_session)).resolve(user.id, raw)

    assert match.canonical_name == canonical, (raw, match)
    assert match.kind in ("GLOBAL_ALIAS", "FUZZY")
    assert match.merchant_id is not None
    assert match.default_category is not None


def test_there_are_at_least_25_variants() -> None:
    assert len(VARIANTS) >= 25


async def test_the_match_carries_the_default_category(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    normalizer = MerchantNormalizer(MerchantRepository(db_session))

    assert (await normalizer.resolve(user.id, "OPET ISTASYONU 4411")).default_category == (
        CategoryKey.FUEL
    )
    assert (await normalizer.resolve(user.id, "TRENDYOL.COM")).default_category == (
        CategoryKey.OTHER
    )


async def test_an_unknown_merchant_is_new_with_a_proposed_name_and_nothing_is_created(
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)
    repository = MerchantRepository(db_session)
    before = len(await repository.list_merchants(user.id))

    match = await MerchantNormalizer(repository).resolve(user.id, "KOSE MANAV KUCUKYALI")

    assert match.kind == "NEW"
    assert match.merchant_id is None
    assert match.canonical_name == "Kose Manav Kucukyali"
    assert "KOSE MANAV KUCUKYALI" in match.alias_keys
    assert (
        len(await repository.list_merchants(user.id)) == before
    )  # no row: created at confirm (P07)


@pytest.mark.parametrize("raw", ["KAHVE", "BAKKAL AHMET", "AYSE ECZANESI", "BIN"])
async def test_generic_or_unrelated_names_are_not_forced_onto_a_merchant(
    raw: str, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)

    match = await MerchantNormalizer(MerchantRepository(db_session)).resolve(user.id, raw)

    assert match.kind == "NEW", (raw, match)


@pytest.mark.parametrize("raw", [None, "", "   ", "...", "&&&"])
async def test_no_name_means_no_match(raw: str | None, db_session: AsyncSession) -> None:
    user = await create_user(db_session)

    match = await MerchantNormalizer(MerchantRepository(db_session)).resolve(user.id, raw)

    assert match.kind == "NONE"


# ---- user aliases ----------------------------------------------------------------------------


async def test_the_users_own_alias_beats_the_global_one(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    repository = MerchantRepository(db_session)
    mine = await repository.create(
        "Benim Bakkal", default_category=CategoryKey.GROCERY,
        alias_keys=["MIGROS"], alias_user_id=user.id,
    )  # fmt: skip

    match = await MerchantNormalizer(repository).resolve(user.id, "MIGROS")

    assert match.kind == "USER_ALIAS"
    assert match.merchant_id == mine.id


async def test_another_users_alias_is_invisible(db_session: AsyncSession) -> None:
    owner = await create_user(db_session, "owner")
    other = await create_user(db_session, "other")
    repository = MerchantRepository(db_session)
    await repository.create(
        "Ozel Dukkan", default_category=CategoryKey.HOME,
        alias_keys=["OZEL DUKKAN LTD"], alias_user_id=owner.id,
    )  # fmt: skip
    normalizer = MerchantNormalizer(repository)

    assert (await normalizer.resolve(owner.id, "OZEL DUKKAN LTD")).kind == "USER_ALIAS"
    assert (await normalizer.resolve(other.id, "OZEL DUKKAN LTD")).kind == "NEW"


async def test_a_seller_tax_number_alias_is_found_before_the_name(
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)
    repository = MerchantRepository(db_session)
    shop = await repository.create(
        "Ornek Elektronik", default_category=CategoryKey.TECHNOLOGY,
        alias_keys=[vkn_alias_key("1234567890")], alias_user_id=user.id,
    )  # fmt: skip

    match = await MerchantNormalizer(repository).resolve(
        user.id, "SOMETHING ELSE ENTIRELY", seller_id="1234567890"
    )

    assert (match.kind, match.merchant_id) == ("USER_ALIAS", shop.id)
    unknown = await MerchantNormalizer(repository).resolve(user.id, None, seller_id="1111111111")
    assert unknown.kind == "NONE"


async def test_repository_functions_refuse_a_missing_user(db_session: AsyncSession) -> None:
    repository = MerchantRepository(db_session)

    with pytest.raises(TypeError):
        await repository.find_aliases(None, ["MIGROS"])  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        await repository.user_rule_category("not-a-uuid", None)  # type: ignore[arg-type]


# ---- creating a merchant (used when the user confirms, P07) ----------------------------------


async def test_create_makes_a_merchant_with_aliases_and_is_idempotent(
    db_session: AsyncSession,
) -> None:
    repository = MerchantRepository(db_session)

    first = await repository.create(
        "Yeni Magaza", default_category=CategoryKey.HOME,
        alias_keys=["YENI MAGAZA", "YENI MAGAZA"], alias_user_id=None,
    )  # fmt: skip
    again = await repository.create(
        "Yeni Magaza", default_category=CategoryKey.HOME,
        alias_keys=["YENI MAGAZA"], alias_user_id=None,
    )  # fmt: skip

    assert first.id == again.id
    assert first.default_category == CategoryKey.HOME
    user = await create_user(db_session)
    match = await MerchantNormalizer(repository).resolve(user.id, "Yeni Magaza")
    assert (match.kind, match.merchant_id) == ("GLOBAL_ALIAS", first.id)
