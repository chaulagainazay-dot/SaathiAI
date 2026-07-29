"""HCG cafeteria domain model (M130+).

Local-first operations application data. Financial amounts live as integer minor
units. Completed financial records are immutable except via correction/reversal.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


SCHEMA_VERSION = "hcg.domain.v1"
DEFAULT_CURRENCY = "NPR"
APP_ID = "saathi.hcg_pos"


class HcgValidationError(ValueError):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code
        self.message = message or code


class OrderState(str, Enum):
    DRAFT = "DRAFT"
    OPEN = "OPEN"
    SUBMITTED = "SUBMITTED"
    PREPARING = "PREPARING"
    READY = "READY"
    SERVED = "SERVED"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    CREDIT = "CREDIT"
    CANCEL_PENDING_APPROVAL = "CANCEL_PENDING_APPROVAL"
    CANCELLED = "CANCELLED"
    REVERSED = "REVERSED"
    CLOSED = "CLOSED"


ORDER_TRANSITIONS: dict[str, frozenset[str]] = {
    OrderState.DRAFT.value: frozenset({OrderState.OPEN.value, OrderState.CANCELLED.value}),
    OrderState.OPEN.value: frozenset(
        {
            OrderState.SUBMITTED.value,
            OrderState.PARTIALLY_PAID.value,
            OrderState.PAID.value,
            OrderState.CREDIT.value,
            OrderState.CANCELLED.value,
            OrderState.CANCEL_PENDING_APPROVAL.value,
        }
    ),
    OrderState.SUBMITTED.value: frozenset(
        {
            OrderState.PREPARING.value,
            OrderState.READY.value,
            OrderState.PARTIALLY_PAID.value,
            OrderState.PAID.value,
            OrderState.CREDIT.value,
            OrderState.CANCEL_PENDING_APPROVAL.value,
            OrderState.CANCELLED.value,
        }
    ),
    OrderState.PREPARING.value: frozenset(
        {
            OrderState.READY.value,
            OrderState.SERVED.value,
            OrderState.PARTIALLY_PAID.value,
            OrderState.PAID.value,
            OrderState.CREDIT.value,
            OrderState.CANCEL_PENDING_APPROVAL.value,
        }
    ),
    OrderState.READY.value: frozenset(
        {
            OrderState.SERVED.value,
            OrderState.PARTIALLY_PAID.value,
            OrderState.PAID.value,
            OrderState.CREDIT.value,
        }
    ),
    OrderState.SERVED.value: frozenset(
        {
            OrderState.PARTIALLY_PAID.value,
            OrderState.PAID.value,
            OrderState.CREDIT.value,
            OrderState.CLOSED.value,
        }
    ),
    OrderState.PARTIALLY_PAID.value: frozenset(
        {
            OrderState.PAID.value,
            OrderState.CREDIT.value,
            OrderState.CLOSED.value,
        }
    ),
    OrderState.PAID.value: frozenset({OrderState.CLOSED.value, OrderState.REVERSED.value}),
    OrderState.CREDIT.value: frozenset({OrderState.CLOSED.value, OrderState.REVERSED.value}),
    OrderState.CANCEL_PENDING_APPROVAL.value: frozenset(
        {OrderState.CANCELLED.value, OrderState.OPEN.value, OrderState.SUBMITTED.value}
    ),
    OrderState.CANCELLED.value: frozenset(),
    OrderState.REVERSED.value: frozenset(),
    OrderState.CLOSED.value: frozenset({OrderState.REVERSED.value}),
}


class PaymentMethod(str, Enum):
    CASH = "CASH"
    QR = "QR"
    CREDIT = "CREDIT"
    MIXED = "MIXED"
    ADJUSTMENT = "ADJUSTMENT"


class PaymentState(str, Enum):
    RECORDED = "RECORDED"
    REVERSED = "REVERSED"
    PENDING_APPROVAL = "PENDING_APPROVAL"


class ShiftState(str, Enum):
    OPEN = "OPEN"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"
    PENDING_REVIEW = "PENDING_REVIEW"


class ReconciliationStatus(str, Enum):
    BALANCED = "BALANCED"
    SHORT = "SHORT"
    OVER = "OVER"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED_VARIANCE = "APPROVED_VARIANCE"
    CORRECTED = "CORRECTED"


class KitchenState(str, Enum):
    QUEUED = "QUEUED"
    ACCEPTED = "ACCEPTED"
    PREPARING = "PREPARING"
    READY = "READY"
    SERVED = "SERVED"
    CANCELLED = "CANCELLED"


KITCHEN_TRANSITIONS: dict[str, frozenset[str]] = {
    KitchenState.QUEUED.value: frozenset(
        {KitchenState.ACCEPTED.value, KitchenState.PREPARING.value, KitchenState.CANCELLED.value}
    ),
    KitchenState.ACCEPTED.value: frozenset(
        {KitchenState.PREPARING.value, KitchenState.CANCELLED.value}
    ),
    KitchenState.PREPARING.value: frozenset(
        {KitchenState.READY.value, KitchenState.CANCELLED.value}
    ),
    KitchenState.READY.value: frozenset({KitchenState.SERVED.value}),
    KitchenState.SERVED.value: frozenset(),
    KitchenState.CANCELLED.value: frozenset(),
}


class StockMovementType(str, Enum):
    OPENING = "OPENING"
    PURCHASE_RECEIPT = "PURCHASE_RECEIPT"
    SALE_CONSUMPTION = "SALE_CONSUMPTION"
    MANUAL_CONSUMPTION = "MANUAL_CONSUMPTION"
    WASTAGE = "WASTAGE"
    ADJUSTMENT_IN = "ADJUSTMENT_IN"
    ADJUSTMENT_OUT = "ADJUSTMENT_OUT"
    REVERSAL = "REVERSAL"


class CreditEntryType(str, Enum):
    OPENING = "OPENING"
    PURCHASE = "PURCHASE"
    REPAYMENT = "REPAYMENT"
    CORRECTION = "CORRECTION"
    REVERSAL = "REVERSAL"


class SupplierEntryType(str, Enum):
    OPENING = "OPENING"
    PURCHASE = "PURCHASE"
    PAYMENT = "PAYMENT"
    SETTLEMENT = "SETTLEMENT"
    CORRECTION = "CORRECTION"
    REVERSAL = "REVERSAL"


class RecordType(str, Enum):
    LOCATION = "location"
    REGISTER = "register"
    SHIFT = "shift"
    STAFF = "staff"
    CUSTOMER = "customer"
    SUPPLIER = "supplier"
    MENU_CATEGORY = "menu_category"
    MENU_ITEM = "menu_item"
    ORDER = "order"
    PAYMENT = "payment"
    CREDIT_ACCOUNT = "credit_account"
    CREDIT_ENTRY = "credit_entry"
    SUPPLIER_ACCOUNT = "supplier_account"
    SUPPLIER_ENTRY = "supplier_entry"
    INVENTORY_ITEM = "inventory_item"
    STOCK_MOVEMENT = "stock_movement"
    RECIPE = "recipe"
    PURCHASE = "purchase"
    EXPENSE = "expense"
    EXPENSE_CATEGORY = "expense_category"
    CASH_MOVEMENT = "cash_movement"
    CASH_RECONCILIATION = "cash_reconciliation"
    KITCHEN_TICKET = "kitchen_ticket"
    ALERT = "alert"
    DAILY_SUMMARY = "daily_summary"
    REPORT_SNAPSHOT = "report_snapshot"
    CORRECTION_REQUEST = "correction_request"
    SETTINGS = "settings"
    META = "meta"


FINANCIAL_IMMUTABLE_TYPES = frozenset(
    {
        RecordType.PAYMENT.value,
        RecordType.CREDIT_ENTRY.value,
        RecordType.SUPPLIER_ENTRY.value,
        RecordType.CASH_MOVEMENT.value,
        RecordType.EXPENSE.value,
        RecordType.PURCHASE.value,
        RecordType.STOCK_MOVEMENT.value,
    }
)


def validate_transition(table: dict[str, frozenset[str]], current: str, nxt: str) -> None:
    allowed = table.get(current, frozenset())
    if nxt not in allowed:
        raise HcgValidationError(
            "ILLEGAL_TRANSITION",
            f"cannot transition {current} → {nxt}",
        )


@dataclass
class HcgRecord:
    record_id: str
    record_type: str
    org_id: str
    workspace_id: str
    app_instance_id: str
    location_id: str = ""
    status: str = "ACTIVE"
    body: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str = ""
    version: int = 1
    created_at: float = 0.0
    updated_at: float = 0.0
    created_by: str = ""
    updated_by: str = ""
    audit_ref: str = ""
    reversed_by: str = ""
    reverses_id: str = ""
    archived_at: float = 0.0
    demo: bool = False

    def to_public(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "record_type": self.record_type,
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
            "app_instance_id": self.app_instance_id,
            "location_id": self.location_id,
            "status": self.status,
            "body": dict(self.body or {}),
            "idempotency_key": self.idempotency_key,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "created_by": self.created_by,
            "updated_by": self.updated_by,
            "audit_ref": self.audit_ref,
            "reversed_by": self.reversed_by,
            "reverses_id": self.reverses_id,
            "archived_at": self.archived_at,
            "demo": self.demo,
            "schema_version": SCHEMA_VERSION,
        }


def order_line_total_minor(qty: int, unit_price_minor: int, discount_minor: int = 0) -> int:
    if qty < 0 or unit_price_minor < 0 or discount_minor < 0:
        raise HcgValidationError("NEGATIVE_AMOUNT", "qty/price/discount must be non-negative")
    if not all(isinstance(x, int) and not isinstance(x, bool) for x in (qty, unit_price_minor, discount_minor)):
        raise HcgValidationError("FLOAT_FORBIDDEN", "integer minor units required")
    gross = qty * unit_price_minor
    if discount_minor > gross:
        raise HcgValidationError("DISCOUNT_EXCEEDS", "discount exceeds line total")
    return gross - discount_minor


def order_totals(lines: list[dict[str, Any]], *, discount_minor: int = 0) -> dict[str, int]:
    subtotal = 0
    for ln in lines:
        subtotal += order_line_total_minor(
            int(ln.get("qty") or 0),
            int(ln.get("unit_price_minor") or 0),
            int(ln.get("discount_minor") or 0),
        )
    disc = int(discount_minor or 0)
    if disc < 0:
        raise HcgValidationError("NEGATIVE_AMOUNT", "order discount negative")
    if disc > subtotal:
        raise HcgValidationError("DISCOUNT_EXCEEDS", "order discount exceeds subtotal")
    return {
        "subtotal_minor": subtotal,
        "discount_minor": disc,
        "total_minor": subtotal - disc,
    }
