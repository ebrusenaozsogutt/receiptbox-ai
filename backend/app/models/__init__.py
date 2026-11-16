"""Importing this package registers every table on `Base.metadata` (Alembic relies on that)."""

from app.models.assistant import AssistantTurn
from app.models.base import Base
from app.models.budget import Budget
from app.models.installment import InstallmentPayment, InstallmentPlan
from app.models.matching import MatchDecision
from app.models.product import Document, Product, ReturnWindow, Warranty
from app.models.reference import Category, Merchant, MerchantAlias, UserCategoryRule
from app.models.reminder import Reminder
from app.models.transaction import Observation, ReceiptItem, Transaction
from app.models.user import RefreshToken, User

__all__ = [
    "AssistantTurn",
    "Base",
    "Budget",
    "Category",
    "Document",
    "InstallmentPayment",
    "InstallmentPlan",
    "MatchDecision",
    "Merchant",
    "MerchantAlias",
    "Observation",
    "Product",
    "ReceiptItem",
    "RefreshToken",
    "Reminder",
    "ReturnWindow",
    "Transaction",
    "User",
    "UserCategoryRule",
    "Warranty",
]
