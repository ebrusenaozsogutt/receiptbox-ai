"""The ORM models and the migrated database must match spec section 6.1."""

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import BigInteger, CheckConstraint, Float, Numeric, UniqueConstraint, text

from app.core.database import create_engine
from app.models import Base
from app.models import enums as e

# Spec 6.1: required columns per table (id / updated_at come from the shared mixins).
REQUIRED_COLUMNS: dict[str, set[str]] = {
    "users": {"email", "password_hash", "is_adult_confirmed", "created_at"},
    "refresh_tokens": {"user_id", "token_hash", "expires_at", "revoked_at", "replaced_by"},
    "categories": {"key", "label_tr", "sort_order"},
    "merchants": {"canonical_name", "default_category_id"},
    "merchant_aliases": {"merchant_id", "alias_normalized", "user_id"},
    "user_category_rules": {"user_id", "merchant_id", "category_id"},
    "transactions": {
        "user_id",
        "merchant_id",
        "merchant_display",
        "category_id",
        "purchase_date",
        "purchase_time",
        "total_minor",
        "currency",
        "payment_type",
        "channel",
        "kind",
        "refund_of_id",
        "is_estimated",
        "note",
        "deleted_at",
    },
    "observations": {
        "user_id",
        "source",
        "status",
        "transaction_id",
        "installment_payment_id",
        "merchant_raw",
        "amount_minor",
        "direction",
        "obs_date",
        "obs_time",
        "installment_seq",
        "installment_count",
        "external_id",
        "fingerprint",
        "masked_text",
        "extraction_json",
        "field_confidence_json",
        "bank_key",
        "created_at",
    },
    "receipt_items": {
        "observation_id",
        "name_raw",
        "quantity",
        "unit_price_minor",
        "total_price_minor",
    },
    "installment_plans": {
        "transaction_id",
        "count",
        "installment_minor",
        "total_payable_minor",
        "first_due_month",
        "status",
    },
    "installment_payments": {"plan_id", "seq", "due_month", "amount_minor", "status"},
    "match_decisions": {
        "user_id",
        "observation_id",
        "transaction_id",
        "installment_payment_id",
        "match_type",
        "score",
        "features_json",
        "decision",
        "decided_at",
    },
    "documents": {
        "user_id",
        "type",
        "storage_key",
        "mime_type",
        "sha256",
        "size_bytes",
        "transaction_id",
        "product_id",
    },
    "products": {
        "user_id",
        "transaction_id",
        "receipt_item_id",
        "name",
        "brand",
        "model",
        "serial_number",
        "product_category",
        "purchase_date",
        "purchase_price_minor",
        "status",
    },
    "warranties": {"product_id", "start_date", "end_date", "source", "confirmed"},
    "return_windows": {"product_id", "end_date", "source", "status"},
    "budgets": {"user_id", "category_id", "monthly_limit_minor"},
    "reminders": {"user_id", "type", "target_id", "fire_at", "delivered_at", "dismissed_at"},
    "assistant_turns": {
        "user_id",
        "question",
        "tool_calls_json",
        "answer",
        "actions_json",
        "latency_ms",
        "created_at",
    },
}

# Spec 6.1: enum columns and their allowed values.
ENUM_COLUMNS: dict[tuple[str, str], set[str]] = {
    ("categories", "key"): {m.value for m in e.CategoryKey},
    ("transactions", "payment_type"): {"SINGLE", "INSTALLMENT"},
    ("transactions", "channel"): {"IN_STORE", "ONLINE", "UNKNOWN"},
    ("transactions", "kind"): {"PURCHASE", "REFUND"},
    ("observations", "source"): {"RECEIPT", "EINVOICE_QR", "BANK_SCREENSHOT", "MANUAL"},
    ("observations", "status"): {"PENDING_REVIEW", "CONFIRMED", "REJECTED", "DUPLICATE"},
    ("observations", "direction"): {"DEBIT", "CREDIT"},
    ("installment_plans", "status"): {"ACTIVE", "COMPLETED", "CANCELLED"},
    ("installment_payments", "status"): {"EXPECTED", "OBSERVED", "INFERRED"},
    ("match_decisions", "match_type"): {"DUPLICATE", "INSTALLMENT"},
    ("match_decisions", "decision"): {
        "PENDING", "ACCEPTED", "REJECTED", "AUTO_ACCEPTED", "UNDONE",
    },
    ("documents", "type"): {"RECEIPT_IMAGE", "INVOICE", "WARRANTY", "OTHER"},
    ("products", "status"): {"ACTIVE", "RETURNED", "ARCHIVED"},
    ("warranties", "source"): {"DOCUMENT", "LEGAL_DEFAULT", "USER"},
    ("return_windows", "source"): {"LEGAL_DEFAULT", "STORE_POLICY", "USER"},
    ("return_windows", "status"): {"OPEN", "CLOSED", "RETURNED"},
    ("reminders", "type"): {
        "WARRANTY_EXPIRY", "RETURN_DEADLINE", "INSTALLMENT_END", "BUDGET_80", "BUDGET_100",
    },
}  # fmt: skip

# Money columns that may be NULL because the amount can be genuinely unknown (owner decision).
NULLABLE_MONEY = {
    ("observations", "amount_minor"),
    ("receipt_items", "unit_price_minor"),
    ("receipt_items", "total_price_minor"),
    ("products", "purchase_price_minor"),
}

USER_OWNED_TABLES = {
    "refresh_tokens", "merchant_aliases", "user_category_rules", "transactions", "observations",
    "match_decisions", "documents", "products", "budgets", "reminders", "assistant_turns",
}  # fmt: skip


def _tables():
    return Base.metadata.tables


def test_exactly_the_19_spec_tables_exist() -> None:
    assert set(_tables()) == set(REQUIRED_COLUMNS)
    assert len(_tables()) == 19


@pytest.mark.parametrize("table_name", sorted(REQUIRED_COLUMNS))
def test_required_columns_exist(table_name: str) -> None:
    columns = {column.name for column in _tables()[table_name].columns}

    assert REQUIRED_COLUMNS[table_name] <= columns, REQUIRED_COLUMNS[table_name] - columns


@pytest.mark.parametrize("table_name", sorted(set(REQUIRED_COLUMNS) - {"user_category_rules"}))
def test_uuid_primary_key_and_timestamps(table_name: str) -> None:
    table = _tables()[table_name]

    assert [column.name for column in table.primary_key.columns] == ["id"]
    assert "gen_random_uuid()" in str(table.c.id.server_default.arg)
    for name in ("created_at", "updated_at"):
        assert table.c[name].type.timezone is True
        assert table.c[name].nullable is False


def test_user_category_rules_primary_key_is_user_and_merchant() -> None:
    table = _tables()["user_category_rules"]

    assert {column.name for column in table.primary_key.columns} == {"user_id", "merchant_id"}


def test_enum_columns_have_exactly_the_spec_values() -> None:
    for (table_name, column_name), expected in ENUM_COLUMNS.items():
        column = _tables()[table_name].c[column_name]
        assert set(column.type.enums) == expected, (table_name, column_name)
        assert column.type.native_enum is False  # VARCHAR + CHECK, used consistently


def test_money_columns_are_bigint_non_negative_and_not_null_except_unknown_amounts() -> None:
    money_columns = [
        (table.name, column)
        for table in _tables().values()
        for column in table.columns
        if column.name.endswith("_minor")
    ]
    # budgets 1, transactions 1, observations 1, receipt_items 2, installment_plans 2,
    # installment_payments 1, products 1
    assert len(money_columns) == 9

    for table_name, column in money_columns:
        assert isinstance(column.type, BigInteger), (table_name, column.name)
        assert column.nullable == ((table_name, column.name) in NULLABLE_MONEY)
        # Column-level CHECKs live on the column, not in table.constraints.
        checks = {str(c.sqltext) for c in column.constraints if isinstance(c, CheckConstraint)}
        assert f"{column.name} >= 0" in checks, (table_name, column.name)


def test_no_float_columns_anywhere() -> None:
    inexact = {
        (table.name, column.name)
        for table in _tables().values()
        for column in table.columns
        if isinstance(column.type, Float | Numeric)
    }

    # Only a fractional quantity (kg) and a matching score. Never money.
    assert inexact == {("receipt_items", "quantity"), ("match_decisions", "score")}


def test_currency_defaults_to_try() -> None:
    column = _tables()["transactions"].c.currency

    assert column.type.length == 3
    assert str(column.server_default.arg) == "TRY"


def test_user_owned_tables_have_user_id_and_others_do_not() -> None:
    with_user_id = {name for name, table in _tables().items() if "user_id" in table.c}

    assert with_user_id == USER_OWNED_TABLES


def _index_names(table_name: str) -> set[str]:
    return {index.name for index in _tables()[table_name].indexes}


def _unique_column_sets(table_name: str) -> set[frozenset[str]]:
    return {
        frozenset(column.name for column in constraint.columns)
        for constraint in _tables()[table_name].constraints
        if isinstance(constraint, UniqueConstraint)
    }


def test_required_indexes_exist() -> None:
    assert "ix_transactions_user_id_purchase_date" in _index_names("transactions")
    assert "ix_transactions_user_id_merchant_id" in _index_names("transactions")
    assert "ix_observations_user_id_fingerprint" in _index_names("observations")
    assert "ix_observations_user_id_external_id" in _index_names("observations")
    assert "ix_installment_payments_plan_id_due_month" in _index_names("installment_payments")
    assert "ix_reminders_user_id_fire_at" in _index_names("reminders")


def test_required_unique_constraints_exist() -> None:
    assert frozenset({"email"}) in _unique_column_sets("users")
    assert frozenset({"key"}) in _unique_column_sets("categories")
    assert frozenset({"alias_normalized", "user_id"}) in _unique_column_sets("merchant_aliases")
    assert frozenset({"transaction_id"}) in _unique_column_sets("installment_plans")
    assert frozenset({"plan_id", "seq"}) in _unique_column_sets("installment_payments")
    assert frozenset({"product_id"}) in _unique_column_sets("warranties")
    assert frozenset({"product_id"}) in _unique_column_sets("return_windows")
    assert frozenset({"user_id", "category_id"}) in _unique_column_sets("budgets")


def test_global_alias_uniqueness_treats_null_user_as_equal() -> None:
    constraint = next(
        c
        for c in _tables()["merchant_aliases"].constraints
        if isinstance(c, UniqueConstraint) and {col.name for col in c.columns} >= {"user_id"}
    )

    assert constraint.dialect_options["postgresql"]["nulls_not_distinct"] is True


def test_one_confirmed_observation_per_source_index_is_unique_and_partial() -> None:
    index = next(
        i
        for i in _tables()["observations"].indexes
        if i.name == "uq_observations_one_confirmed_per_source"
    )

    assert index.unique is True
    assert [column.name for column in index.columns] == ["transaction_id", "source"]
    assert "CONFIRMED" in str(index.dialect_options["postgresql"]["where"])


# ---- the migrated database ----------------------------------------------------------------


async def test_migrated_database_has_no_drift_from_the_models(migrated_database: str) -> None:
    engine = create_engine(migrated_database)
    try:
        async with engine.connect() as connection:
            diff = await connection.run_sync(
                lambda sync_connection: compare_metadata(
                    MigrationContext.configure(sync_connection, opts={"compare_type": True}),
                    Base.metadata,
                )
            )
    finally:
        await engine.dispose()

    assert diff == []


async def test_migrated_database_has_all_check_constraints(migrated_database: str) -> None:
    """Alembic does not compare CHECK constraints, so verify them against the catalog."""
    engine = create_engine(migrated_database)
    try:
        async with engine.connect() as connection:
            rows = await connection.execute(
                text("SELECT conname FROM pg_constraint WHERE contype = 'c'")
            )
            present = {row[0] for row in rows}
    finally:
        await engine.dispose()

    expected = {f"ck_{table}_{column}" for (table, column) in ENUM_COLUMNS}
    expected |= {
        f"ck_{table.name}_{column.name}_nonneg"
        for table in _tables().values()
        for column in table.columns
        if column.name.endswith("_minor")
    }
    expected |= {
        "ck_users_email_lowercase",
        "ck_installment_plans_count_positive",
        "ck_installment_plans_first_due_month_day_one",
        "ck_installment_payments_seq_positive",
        "ck_installment_payments_due_month_day_one",
        "ck_warranties_start_not_after_end",
        "ck_documents_size_bytes_nonneg",
    }
    assert expected <= present, sorted(expected - present)
