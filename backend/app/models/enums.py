"""Enumerations from spec section 6.1. Stored as VARCHAR + CHECK (not native PostgreSQL enums)."""

from enum import StrEnum


class CategoryKey(StrEnum):
    """The fixed 13 categories (spec 5.7)."""

    GROCERY = "GROCERY"
    FOOD_DRINK = "FOOD_DRINK"
    TRANSPORT = "TRANSPORT"
    FUEL = "FUEL"
    CLOTHING = "CLOTHING"
    TECHNOLOGY = "TECHNOLOGY"
    HOME = "HOME"
    HEALTH_CARE = "HEALTH_CARE"
    ENTERTAINMENT = "ENTERTAINMENT"
    SUBSCRIPTION = "SUBSCRIPTION"
    EDUCATION = "EDUCATION"
    BILLS = "BILLS"
    OTHER = "OTHER"


class PaymentType(StrEnum):
    SINGLE = "SINGLE"
    INSTALLMENT = "INSTALLMENT"


class Channel(StrEnum):
    IN_STORE = "IN_STORE"
    ONLINE = "ONLINE"
    UNKNOWN = "UNKNOWN"


class TransactionKind(StrEnum):
    PURCHASE = "PURCHASE"
    REFUND = "REFUND"


class ObservationSource(StrEnum):
    RECEIPT = "RECEIPT"
    EINVOICE_QR = "EINVOICE_QR"
    BANK_SCREENSHOT = "BANK_SCREENSHOT"
    MANUAL = "MANUAL"


class ObservationStatus(StrEnum):
    PENDING_REVIEW = "PENDING_REVIEW"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    DUPLICATE = "DUPLICATE"


class Direction(StrEnum):
    """Money direction of an observation. Amounts themselves are always >= 0."""

    DEBIT = "DEBIT"  # money left the user's account (a purchase)
    CREDIT = "CREDIT"  # money came back (a refund)


class InstallmentPlanStatus(StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class InstallmentPaymentStatus(StrEnum):
    EXPECTED = "EXPECTED"
    OBSERVED = "OBSERVED"
    INFERRED = "INFERRED"


class MatchType(StrEnum):
    DUPLICATE = "DUPLICATE"
    INSTALLMENT = "INSTALLMENT"


class MatchDecisionStatus(StrEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    AUTO_ACCEPTED = "AUTO_ACCEPTED"
    UNDONE = "UNDONE"


class DocumentType(StrEnum):
    RECEIPT_IMAGE = "RECEIPT_IMAGE"
    INVOICE = "INVOICE"
    WARRANTY = "WARRANTY"
    OTHER = "OTHER"


class ProductStatus(StrEnum):
    ACTIVE = "ACTIVE"
    RETURNED = "RETURNED"
    ARCHIVED = "ARCHIVED"


class WarrantySource(StrEnum):
    DOCUMENT = "DOCUMENT"
    LEGAL_DEFAULT = "LEGAL_DEFAULT"
    USER = "USER"


class ReturnWindowSource(StrEnum):
    LEGAL_DEFAULT = "LEGAL_DEFAULT"
    STORE_POLICY = "STORE_POLICY"
    USER = "USER"


class ReturnWindowStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    RETURNED = "RETURNED"


class ReminderType(StrEnum):
    WARRANTY_EXPIRY = "WARRANTY_EXPIRY"
    RETURN_DEADLINE = "RETURN_DEADLINE"
    INSTALLMENT_END = "INSTALLMENT_END"
    BUDGET_80 = "BUDGET_80"
    BUDGET_100 = "BUDGET_100"
