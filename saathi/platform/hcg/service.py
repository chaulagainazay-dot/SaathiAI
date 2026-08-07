"""HCG cafeteria operations service (M130–M138).

Runs inside Universal Application Runtime. Mutations: auth → RBAC → domain
validation → approval when required → transaction → evidence → audit → notify.
Conversation/Yeti never mutates financial records directly.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from saathi.platform.context import PlatformContextError
from saathi.platform.models import PlatformPermission, new_id
from saathi.platform.safety.models import is_agent_actor

from .models import (
    APP_ID,
    DEFAULT_CURRENCY,
    SCHEMA_VERSION,
    CreditEntryType,
    HcgValidationError,
    KitchenState,
    KITCHEN_TRANSITIONS,
    OrderState,
    ORDER_TRANSITIONS,
    PaymentMethod,
    PaymentState,
    ReconciliationStatus,
    RecordType,
    ShiftState,
    StockMovementType,
    SupplierEntryType,
    order_totals,
    validate_transition,
)
from .money import Money, MoneyError, parse_money_input
from .repository import HcgRepository

SENSITIVE_ACTIONS = frozenset(
    {
        "payment.reverse",
        "order.cancel_completed",
        "shift.modify_closed",
        "reconciliation.overwrite",
        "expense.reverse",
        "credit.reduce_without_repayment",
        "supplier.reduce_without_settlement",
        "inventory.large_adjustment",
        "restore.overwrite",
        "bulk.correction",
    }
)


class HcgService:
    def __init__(self, platform_store, *, platform=None):
        self.store = platform_store
        self.platform = platform
        self.repo = HcgRepository(platform_store)

    # ── guards ───────────────────────────────────────────────────────────
    @staticmethod
    def _human(ctx) -> None:
        if is_agent_actor(ctx):
            raise PlatformContextError(
                "PERMISSION_DENIED",
                "HCG financial mutations require a human operator session",
            )

    def _perm(self, ctx, permission: PlatformPermission) -> None:
        ctx.require_permission(permission)

    def _scope_key(self, ctx) -> tuple[str, str]:
        return ctx.org_id, ctx.workspace_id

    def _instance(self, ctx, app_instance_id: str = "") -> str:
        if app_instance_id:
            return app_instance_id
        # Prefer install from AppRuntime if available
        if self.platform is not None:
            try:
                from saathi.platform.apps import default_app_runtime

                rt = default_app_runtime(self.platform)
                app = rt.get_app(ctx, APP_ID)
                install = (app.get("app") or {}).get("install_id") or ""
                if install:
                    return install
            except Exception:
                pass
        return f"hcg:{ctx.org_id}:{ctx.workspace_id}"

    def _audit(self, ctx, event: str, *, outcome: str = "success",
               detail: dict | None = None, evidence: str = "") -> None:
        self.store.append_audit(
            event,
            user_id=ctx.user_id,
            role=ctx.role,
            org_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            project_id=getattr(ctx, "project_id", ""),
            mission_id=getattr(ctx, "mission_id", ""),
            outcome=outcome,
            evidence=evidence[:500],
            detail=detail or {},
        )

    def _notify(self, ctx, *, title: str, summary: str, event_type: str,
                related_object: str = "", severity: str = "info",
                dedupe_key: str = "") -> None:
        self.store.create_notification(
            org_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            user_id=ctx.user_id,
            type=event_type,
            title=title[:200],
            summary=summary[:500],
            severity=severity,
            actor=f"user:{ctx.user_id}",
            related_object=related_object,
            related_type="hcg",
            evidence="",
            dedupe_key=dedupe_key or f"{event_type}:{related_object}",
        )

    def _require_approval(self, ctx, *, action: str, approval_reference: str = "",
                          target: str = "") -> str:
        if action not in SENSITIVE_ACTIONS:
            return ""
        if not approval_reference:
            raise PlatformContextError(
                "APPROVAL_REQUIRED",
                f"sensitive HCG action requires approval: {action}",
            )
        # Validate against Approval Center if platform present
        if self.platform is not None:
            rec = self.store.get_approval(approval_reference)
            if not rec:
                raise PlatformContextError("APPROVAL_NOT_FOUND", approval_reference)
            if rec.org_id != ctx.org_id or rec.workspace_id != ctx.workspace_id:
                raise PlatformContextError("APPROVAL_ISOLATION", "cross-scope approval denied")
            if rec.status not in ("approved", "APPROVED"):
                # allow pending consumed flow — must be approved
                from saathi.platform.models import ApprovalStatus

                if rec.status != ApprovalStatus.APPROVED.value:
                    raise PlatformContextError(
                        "APPROVAL_NOT_APPROVED",
                        f"status={rec.status}",
                    )
        return approval_reference

    def _ev(self, ctx, record, event_type: str, summary: str, **detail) -> dict:
        return self.repo.evidence(
            org_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            app_instance_id=record.app_instance_id,
            record_id=record.record_id,
            event_type=event_type,
            summary=summary,
            actor=ctx.user_id,
            detail=detail,
        )

    # ── bootstrap / seed ─────────────────────────────────────────────────
    def ensure_seeded(self, ctx, *, app_instance_id: str = "", force: bool = False) -> dict:
        """Install deterministic demo data once per workspace instance."""
        self._perm(ctx, PlatformPermission.HCG_DASHBOARD_READ)
        iid = self._instance(ctx, app_instance_id)
        existing = self.repo.list(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            record_type=RecordType.META.value, limit=5,
        )
        if existing and not force:
            return {"seeded": False, "app_instance_id": iid, "meta": existing[0].to_public()}
        from .seed import build_seed_payload

        payload = build_seed_payload()
        created = 0
        by_key: dict[str, str] = {}
        for item in payload:
            rec = self.repo.create(
                record_type=item["record_type"],
                org_id=ctx.org_id,
                workspace_id=ctx.workspace_id,
                app_instance_id=iid,
                body=item["body"],
                status=item.get("status", "ACTIVE"),
                location_id=item.get("location_id", ""),
                created_by=ctx.user_id,
                idempotency_key=item.get("idempotency_key", ""),
                demo=True,
            )
            if item.get("idempotency_key"):
                by_key[item["idempotency_key"]] = rec.record_id
            created += 1
        # Wire recipe_id on Dal Bhat menu item to actual recipe record_id
        recipe_rid = by_key.get("seed:recipe:recipe-dalbhat")
        menu_rid = by_key.get("seed:menu:menu-dalbhat")
        if recipe_rid and menu_rid:
            mi = self.repo.get(
                menu_rid, org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            )
            if mi:
                self.repo.update_mutable(
                    mi, body_updates={"recipe_id": recipe_rid}, updated_by=ctx.user_id,
                )
        # Remap inventory body IDs used in recipe ingredients to real record_ids
        if recipe_rid:
            inv_map = {
                "inv-rice": by_key.get("seed:inv:inv-rice"),
                "inv-dal": by_key.get("seed:inv:inv-dal"),
                "inv-tea": by_key.get("seed:inv:inv-tea"),
                "inv-oil": by_key.get("seed:inv:inv-oil"),
            }
            recipe = self.repo.get(
                recipe_rid, org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            )
            if recipe:
                ings = []
                for ing in (recipe.body or {}).get("ingredients") or []:
                    real = inv_map.get(ing.get("inventory_item_id")) or ing.get("inventory_item_id")
                    ings.append({**ing, "inventory_item_id": real})
                self.repo.update_mutable(
                    recipe, body_updates={"ingredients": ings}, updated_by=ctx.user_id,
                )
        meta = self.repo.create(
            record_type=RecordType.META.value,
            org_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            app_instance_id=iid,
            body={
                "schema_version": SCHEMA_VERSION,
                "seeded": True,
                "label": "demo/certification data",
                "currency": DEFAULT_CURRENCY,
                "consumption_mode": "automatic",
            },
            status="ACTIVE",
            created_by=ctx.user_id,
            idempotency_key=f"meta:{iid}",
            demo=True,
        )
        self._audit(ctx, "hcg.seeded", detail={"records": created, "app_instance_id": iid})
        return {"seeded": True, "records": created + 1, "app_instance_id": iid, "meta": meta.to_public()}

    # ── dashboard / health ───────────────────────────────────────────────
    def dashboard(self, ctx, *, app_instance_id: str = "") -> dict:
        self._perm(ctx, PlatformPermission.HCG_DASHBOARD_READ)
        iid = self._instance(ctx, app_instance_id)
        self.ensure_seeded(ctx, app_instance_id=iid)
        orders = self.repo.list(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            record_type=RecordType.ORDER.value, limit=500,
        )
        payments = self.repo.list(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            record_type=RecordType.PAYMENT.value, limit=500,
        )
        expenses = self.repo.list(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            record_type=RecordType.EXPENSE.value, limit=500,
        )
        inventory = self.repo.list(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            record_type=RecordType.INVENTORY_ITEM.value, limit=500,
        )
        kitchen = self.repo.list(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            record_type=RecordType.KITCHEN_TICKET.value, limit=200,
        )
        shifts = self.repo.list(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            record_type=RecordType.SHIFT.value, limit=50,
        )
        credit_entries = self.repo.list(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            record_type=RecordType.CREDIT_ENTRY.value, limit=500,
        )
        supplier_entries = self.repo.list(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            record_type=RecordType.SUPPLIER_ENTRY.value, limit=500,
        )
        alerts = self.repo.list(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            record_type=RecordType.ALERT.value, limit=50,
        )

        sales_today = 0
        cash_received = 0
        qr_received = 0
        credit_sales = 0
        order_count = 0
        for o in orders:
            if o.status in (
                OrderState.CANCELLED.value,
                OrderState.REVERSED.value,
                OrderState.DRAFT.value,
            ):
                continue
            order_count += 1
            sales_today += int((o.body or {}).get("total_minor") or 0)
        for p in payments:
            if p.status == PaymentState.REVERSED.value:
                continue
            amt = int((p.body or {}).get("amount_minor") or 0)
            method = (p.body or {}).get("method")
            if method == PaymentMethod.CASH.value:
                cash_received += amt
            elif method == PaymentMethod.QR.value:
                qr_received += amt
            elif method == PaymentMethod.CREDIT.value:
                credit_sales += amt

        expense_total = sum(
            int((e.body or {}).get("amount_minor") or 0)
            for e in expenses
            if e.status != "REVERSED"
        )
        low_stock = [
            i.to_public()
            for i in inventory
            if int((i.body or {}).get("qty_on_hand") or 0)
            <= int((i.body or {}).get("min_qty") or 0)
        ]
        active_kitchen = [
            k.to_public()
            for k in kitchen
            if k.status in (
                KitchenState.QUEUED.value,
                KitchenState.ACCEPTED.value,
                KitchenState.PREPARING.value,
                KitchenState.READY.value,
            )
        ]
        open_shifts = [s.to_public() for s in shifts if s.status == ShiftState.OPEN.value]

        customer_credit = self._ledger_balance(credit_entries, field_sign=1)
        supplier_dues = self._ledger_balance(supplier_entries, field_sign=1)

        return {
            "label": "demo/certification data — not live HCG production",
            "currency": DEFAULT_CURRENCY,
            "app_instance_id": iid,
            "schema_version": SCHEMA_VERSION,
            "metrics": {
                "sales_today_minor": sales_today,
                "order_count": order_count,
                "cash_received_minor": cash_received,
                "qr_received_minor": qr_received,
                "credit_sales_minor": credit_sales,
                "expenses_minor": expense_total,
                "net_cash_movement_minor": cash_received - expense_total,
                "customer_credit_outstanding_minor": customer_credit,
                "supplier_dues_minor": supplier_dues,
                "low_stock_count": len(low_stock),
                "active_kitchen_tickets": len(active_kitchen),
                "open_shift_count": len(open_shifts),
                "alert_count": len([a for a in alerts if a.status != "RESOLVED"]),
            },
            "low_stock": low_stock[:20],
            "active_kitchen": active_kitchen[:20],
            "open_shifts": open_shifts,
            "recent_alerts": [a.to_public() for a in alerts[:10]],
            "derived_from_authoritative_records": True,
            "fabricated": False,
        }

    @staticmethod
    def _ledger_balance(entries, *, field_sign: int = 1) -> int:
        bal = 0
        for e in entries:
            if e.status == "REVERSED":
                continue
            body = e.body or {}
            delta = int(body.get("delta_minor") or 0)
            bal += delta * field_sign
        return bal

    def health(self, ctx, *, app_instance_id: str = "") -> dict:
        self._perm(ctx, PlatformPermission.HCG_DASHBOARD_READ)
        iid = self._instance(ctx, app_instance_id)
        try:
            n = self.repo.count(
                org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            )
            db_ok = True
        except Exception as exc:  # noqa: BLE001
            n = 0
            db_ok = False
            err = str(exc)[:120]
        else:
            err = ""
        dash = self.dashboard(ctx, app_instance_id=iid) if db_ok else {}
        m = dash.get("metrics") or {}
        return {
            "status": "HEALTHY" if db_ok else "UNHEALTHY",
            "schema_version": SCHEMA_VERSION,
            "app_id": APP_ID,
            "app_instance_id": iid,
            "record_count": n,
            "database_health": "ok" if db_ok else f"error:{err}",
            "active_shift_count": m.get("open_shift_count", 0),
            "low_stock_count": m.get("low_stock_count", 0),
            "active_kitchen_tickets": m.get("active_kitchen_tickets", 0),
            "customer_credit_outstanding_minor": m.get("customer_credit_outstanding_minor", 0),
            "supplier_dues_minor": m.get("supplier_dues_minor", 0),
            "production_authorized": False,
            "marketplace": False,
            "local_only": True,
        }

    # ── menu ─────────────────────────────────────────────────────────────
    def list_menu(self, ctx, *, app_instance_id: str = "", q: str = "") -> dict:
        self._perm(ctx, PlatformPermission.HCG_MENU_READ)
        iid = self._instance(ctx, app_instance_id)
        self.ensure_seeded(ctx, app_instance_id=iid)
        cats = self.repo.list(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            record_type=RecordType.MENU_CATEGORY.value, limit=100,
        )
        items = self.repo.list(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            record_type=RecordType.MENU_ITEM.value, q=q, limit=200,
        )
        return {
            "categories": [c.to_public() for c in cats],
            "items": [i.to_public() for i in items if i.status != "INACTIVE"],
        }

    def upsert_menu_item(self, ctx, *, name: str, category_id: str, price_minor: int,
                         available: bool = True, favorite: bool = False,
                         recipe_id: str = "", station: str = "main",
                         app_instance_id: str = "", item_id: str = "") -> dict:
        self._human(ctx)
        self._perm(ctx, PlatformPermission.HCG_MENU_MANAGE)
        iid = self._instance(ctx, app_instance_id)
        if not isinstance(price_minor, int) or isinstance(price_minor, bool) or price_minor < 0:
            raise PlatformContextError("INVALID_MONEY", "price_minor must be non-negative int")
        body = {
            "name": (name or "")[:120],
            "category_id": category_id,
            "price_minor": price_minor,
            "currency": DEFAULT_CURRENCY,
            "available": bool(available),
            "favorite": bool(favorite),
            "recipe_id": recipe_id,
            "station": station[:40],
        }
        if item_id:
            rec = self.repo.get(item_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid)
            if not rec or rec.record_type != RecordType.MENU_ITEM.value:
                raise PlatformContextError("NOT_FOUND", item_id)
            # New price does not rewrite historical orders (snapshot on order lines)
            rec = self.repo.update_mutable(rec, body_updates=body, updated_by=ctx.user_id)
        else:
            rec = self.repo.create(
                record_type=RecordType.MENU_ITEM.value,
                org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
                body=body, created_by=ctx.user_id,
            )
        self._ev(ctx, rec, "menu.item.upsert", f"Menu item {body['name']}")
        self._audit(ctx, "hcg.menu.upsert", detail={"record_id": rec.record_id})
        return {"item": rec.to_public()}

    # ── orders ───────────────────────────────────────────────────────────
    def create_order(
        self,
        ctx,
        *,
        lines: list[dict],
        channel: str = "dine_in",
        customer_id: str = "",
        table_ref: str = "",
        notes: str = "",
        discount_minor: int = 0,
        idempotency_key: str = "",
        app_instance_id: str = "",
        shift_id: str = "",
    ) -> dict:
        self._human(ctx)
        self._perm(ctx, PlatformPermission.HCG_ORDER_CREATE)
        iid = self._instance(ctx, app_instance_id)
        if idempotency_key:
            hit = self.repo.find_idempotent(
                org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
                record_type=RecordType.ORDER.value, idempotency_key=idempotency_key,
            )
            if hit:
                return {"order": hit.to_public(), "idempotent_replay": True}

        snap_lines = []
        for raw in lines or []:
            menu_id = raw.get("menu_item_id") or ""
            qty = int(raw.get("qty") or 0)
            if qty <= 0:
                raise PlatformContextError("INVALID_QTY", "qty must be positive")
            unit = raw.get("unit_price_minor")
            name = raw.get("name") or ""
            if menu_id and unit is None:
                mi = self.repo.get(
                    menu_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
                )
                if not mi:
                    raise PlatformContextError("MENU_NOT_FOUND", menu_id)
                unit = int((mi.body or {}).get("price_minor") or 0)
                name = name or (mi.body or {}).get("name") or ""
            unit = int(unit or 0)
            if unit < 0 or isinstance(unit, bool):
                raise PlatformContextError("INVALID_MONEY", "unit price invalid")
            disc = int(raw.get("discount_minor") or 0)
            snap_lines.append(
                {
                    "menu_item_id": menu_id,
                    "name": name[:120],
                    "qty": qty,
                    "unit_price_minor": unit,
                    "discount_minor": disc,
                    "currency": DEFAULT_CURRENCY,
                    "notes": (raw.get("notes") or "")[:200],
                }
            )
        if not snap_lines:
            raise PlatformContextError("EMPTY_ORDER", "order needs lines")
        totals = order_totals(snap_lines, discount_minor=int(discount_minor or 0))
        token = new_id("tok")[-6:].upper()
        body = {
            "lines": snap_lines,
            **totals,
            "currency": DEFAULT_CURRENCY,
            "channel": channel[:40],
            "customer_id": customer_id,
            "table_ref": table_ref[:40],
            "notes": notes[:500],
            "token": token,
            "paid_minor": 0,
            "balance_minor": totals["total_minor"],
            "shift_id": shift_id,
            "payment_ids": [],
        }
        rec = self.repo.create(
            record_type=RecordType.ORDER.value,
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            body=body, status=OrderState.OPEN.value, created_by=ctx.user_id,
            idempotency_key=idempotency_key,
        )
        self._ev(ctx, rec, "order.created", f"Order {token} total={totals['total_minor']}")
        self._audit(ctx, "hcg.order.created", detail={"order_id": rec.record_id, "total_minor": totals["total_minor"]})
        return {"order": rec.to_public(), "idempotent_replay": False}

    def get_order(self, ctx, order_id: str, *, app_instance_id: str = "") -> dict:
        self._perm(ctx, PlatformPermission.HCG_ORDER_READ)
        iid = self._instance(ctx, app_instance_id)
        rec = self.repo.get(order_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid)
        if not rec or rec.record_type != RecordType.ORDER.value:
            raise PlatformContextError("NOT_FOUND", order_id)
        return {"order": rec.to_public()}

    def list_orders(self, ctx, *, app_instance_id: str = "", status: str = "",
                    q: str = "", limit: int = 100) -> dict:
        self._perm(ctx, PlatformPermission.HCG_ORDER_READ)
        iid = self._instance(ctx, app_instance_id)
        rows = self.repo.list(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            record_type=RecordType.ORDER.value, status=status, q=q, limit=limit,
        )
        return {"orders": [r.to_public() for r in rows], "count": len(rows)}

    def submit_to_kitchen(self, ctx, order_id: str, *, app_instance_id: str = "") -> dict:
        self._human(ctx)
        self._perm(ctx, PlatformPermission.HCG_ORDER_UPDATE)
        iid = self._instance(ctx, app_instance_id)
        order = self.repo.get(order_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid)
        if not order or order.record_type != RecordType.ORDER.value:
            raise PlatformContextError("NOT_FOUND", order_id)
        validate_transition(ORDER_TRANSITIONS, order.status, OrderState.SUBMITTED.value)
        order = self.repo.update_mutable(
            order, status=OrderState.SUBMITTED.value, updated_by=ctx.user_id,
        )
        tickets = []
        for ln in (order.body or {}).get("lines") or []:
            t = self.repo.create(
                record_type=RecordType.KITCHEN_TICKET.value,
                org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
                body={
                    "order_id": order.record_id,
                    "token": (order.body or {}).get("token"),
                    "item_name": ln.get("name"),
                    "qty": ln.get("qty"),
                    "notes": ln.get("notes") or "",
                    "station": "main",
                    "priority": 0,
                },
                status=KitchenState.QUEUED.value,
                created_by=ctx.user_id,
            )
            tickets.append(t.to_public())
        self._ev(ctx, order, "order.submitted_kitchen", "Submitted to kitchen")
        return {"order": order.to_public(), "tickets": tickets}

    def transition_kitchen(self, ctx, ticket_id: str, *, to_state: str,
                           app_instance_id: str = "") -> dict:
        self._human(ctx)
        self._perm(ctx, PlatformPermission.HCG_KITCHEN_MANAGE)
        iid = self._instance(ctx, app_instance_id)
        t = self.repo.get(ticket_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid)
        if not t or t.record_type != RecordType.KITCHEN_TICKET.value:
            raise PlatformContextError("NOT_FOUND", ticket_id)
        validate_transition(KITCHEN_TRANSITIONS, t.status, to_state)
        t = self.repo.update_mutable(t, status=to_state, updated_by=ctx.user_id)
        # Mirror order prep states
        order_id = (t.body or {}).get("order_id")
        if order_id and to_state in (KitchenState.PREPARING.value, KitchenState.READY.value, KitchenState.SERVED.value):
            order = self.repo.get(order_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid)
            if order and order.status == OrderState.SUBMITTED.value and to_state == KitchenState.PREPARING.value:
                try:
                    validate_transition(ORDER_TRANSITIONS, order.status, OrderState.PREPARING.value)
                    self.repo.update_mutable(order, status=OrderState.PREPARING.value, updated_by=ctx.user_id)
                except HcgValidationError:
                    pass
            if order and to_state == KitchenState.READY.value:
                try:
                    validate_transition(ORDER_TRANSITIONS, order.status, OrderState.READY.value)
                    order = self.repo.get(order_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid)
                    if order:
                        self.repo.update_mutable(order, status=OrderState.READY.value, updated_by=ctx.user_id)
                except HcgValidationError:
                    pass
        self._ev(ctx, t, "kitchen.transition", f"Kitchen → {to_state}")
        return {"ticket": t.to_public()}

    def list_kitchen(self, ctx, *, app_instance_id: str = "") -> dict:
        self._perm(ctx, PlatformPermission.HCG_KITCHEN_READ)
        iid = self._instance(ctx, app_instance_id)
        rows = self.repo.list(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            record_type=RecordType.KITCHEN_TICKET.value, limit=200,
        )
        return {"tickets": [r.to_public() for r in rows]}

    # ── payments ─────────────────────────────────────────────────────────
    def record_payment(
        self,
        ctx,
        *,
        order_id: str,
        amount_minor: int,
        method: str,
        qr_reference: str = "",
        customer_id: str = "",
        shift_id: str = "",
        idempotency_key: str = "",
        app_instance_id: str = "",
        note: str = "",
    ) -> dict:
        self._human(ctx)
        self._perm(ctx, PlatformPermission.HCG_PAYMENT_RECORD)
        iid = self._instance(ctx, app_instance_id)
        try:
            money = Money.from_minor(amount_minor, DEFAULT_CURRENCY).require_positive()
        except MoneyError as e:
            raise PlatformContextError("INVALID_MONEY", str(e)) from e
        method = (method or "").upper()
        if method not in {m.value for m in PaymentMethod}:
            raise PlatformContextError("INVALID_METHOD", method)
        if method == PaymentMethod.QR.value and not (qr_reference or "").strip():
            raise PlatformContextError("QR_REF_REQUIRED", "manual QR reference required")

        if idempotency_key:
            hit = self.repo.find_idempotent(
                org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
                record_type=RecordType.PAYMENT.value, idempotency_key=idempotency_key,
            )
            if hit:
                return {"payment": hit.to_public(), "idempotent_replay": True}

        # Duplicate QR reference protection
        if qr_reference:
            existing_pays = self.repo.list(
                org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
                record_type=RecordType.PAYMENT.value, q=qr_reference, limit=50,
            )
            for p in existing_pays:
                if p.status != PaymentState.REVERSED.value and (p.body or {}).get("qr_reference") == qr_reference:
                    raise PlatformContextError("DUPLICATE_PAYMENT_REF", qr_reference)

        order = self.repo.get(order_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid)
        if not order or order.record_type != RecordType.ORDER.value:
            raise PlatformContextError("NOT_FOUND", order_id)
        if order.status in (
            OrderState.CANCELLED.value,
            OrderState.REVERSED.value,
            OrderState.CLOSED.value,
        ):
            raise PlatformContextError("ORDER_CLOSED", order.status)

        balance = int((order.body or {}).get("balance_minor") or 0)
        if money.amount_minor > balance:
            raise PlatformContextError("PAYMENT_EXCEEDS_BALANCE", f"{money.amount_minor}>{balance}")

        # Shift state check when provided
        if shift_id:
            sh = self.repo.get(shift_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid)
            if not sh or sh.status != ShiftState.OPEN.value:
                raise PlatformContextError("SHIFT_INVALID", "payment requires open shift")

        pay = self.repo.create(
            record_type=RecordType.PAYMENT.value,
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            body={
                "order_id": order_id,
                "amount_minor": money.amount_minor,
                "currency": DEFAULT_CURRENCY,
                "method": method,
                "qr_reference": (qr_reference or "")[:120],
                "customer_id": customer_id or (order.body or {}).get("customer_id") or "",
                "shift_id": shift_id or (order.body or {}).get("shift_id") or "",
                "note": note[:200],
                "manual_qr": method == PaymentMethod.QR.value,
                "live_gateway": False,
            },
            status=PaymentState.RECORDED.value,
            created_by=ctx.user_id,
            idempotency_key=idempotency_key,
        )

        paid = int((order.body or {}).get("paid_minor") or 0) + money.amount_minor
        new_balance = int((order.body or {}).get("total_minor") or 0) - paid
        pay_ids = list((order.body or {}).get("payment_ids") or [])
        pay_ids.append(pay.record_id)
        if new_balance <= 0:
            new_status = OrderState.CREDIT.value if method == PaymentMethod.CREDIT.value and paid > 0 else OrderState.PAID.value
            if method == PaymentMethod.CREDIT.value:
                new_status = OrderState.CREDIT.value
            elif paid >= int((order.body or {}).get("total_minor") or 0):
                new_status = OrderState.PAID.value
            else:
                new_status = OrderState.PARTIALLY_PAID.value
        else:
            new_status = OrderState.PARTIALLY_PAID.value
            if method == PaymentMethod.CREDIT.value and new_balance == 0:
                new_status = OrderState.CREDIT.value

        # refine status
        total = int((order.body or {}).get("total_minor") or 0)
        if paid >= total:
            new_status = OrderState.CREDIT.value if method == PaymentMethod.CREDIT.value else OrderState.PAID.value
            # if mixed credit portion already recorded as CREDIT method fully settling
            if method == PaymentMethod.CREDIT.value:
                new_status = OrderState.CREDIT.value
            new_balance = 0
        else:
            new_status = OrderState.PARTIALLY_PAID.value

        try:
            validate_transition(ORDER_TRANSITIONS, order.status, new_status)
        except HcgValidationError:
            # allow from READY/SERVED etc.
            if new_status not in (
                OrderState.PAID.value,
                OrderState.CREDIT.value,
                OrderState.PARTIALLY_PAID.value,
            ):
                raise

        order = self.repo.update_mutable(
            order,
            status=new_status,
            body_updates={
                "paid_minor": paid,
                "balance_minor": new_balance,
                "payment_ids": pay_ids,
            },
            updated_by=ctx.user_id,
        )

        # Cash movement for cash payments
        if method == PaymentMethod.CASH.value:
            self.repo.create(
                record_type=RecordType.CASH_MOVEMENT.value,
                org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
                body={
                    "kind": "SALE",
                    "amount_minor": money.amount_minor,
                    "currency": DEFAULT_CURRENCY,
                    "shift_id": shift_id or (order.body or {}).get("shift_id") or "",
                    "payment_id": pay.record_id,
                    "order_id": order_id,
                },
                status="RECORDED",
                created_by=ctx.user_id,
            )

        # Credit ledger on credit payment
        if method == PaymentMethod.CREDIT.value:
            cust = customer_id or (order.body or {}).get("customer_id") or ""
            if not cust:
                raise PlatformContextError("CUSTOMER_REQUIRED", "credit payment needs customer")
            self._append_credit(
                ctx, iid, customer_id=cust, delta_minor=money.amount_minor,
                entry_type=CreditEntryType.PURCHASE.value, ref=pay.record_id,
                note=f"Credit sale order {order_id}",
            )

        # Recipe consumption on full payment
        if new_status in (OrderState.PAID.value, OrderState.CREDIT.value):
            self._consume_for_order(ctx, iid, order)

        self._ev(ctx, pay, "payment.recorded", f"{method} {money.amount_minor}")
        self._audit(
            ctx, "hcg.payment.recorded",
            detail={"payment_id": pay.record_id, "method": method, "amount_minor": money.amount_minor},
        )
        return {"payment": pay.to_public(), "order": order.to_public(), "idempotent_replay": False}

    def reverse_payment(
        self, ctx, payment_id: str, *, approval_reference: str = "",
        reason: str = "", app_instance_id: str = "",
    ) -> dict:
        self._human(ctx)
        self._perm(ctx, PlatformPermission.HCG_PAYMENT_REVERSE)
        appr = self._require_approval(
            ctx, action="payment.reverse", approval_reference=approval_reference, target=payment_id,
        )
        iid = self._instance(ctx, app_instance_id)
        pay = self.repo.get(payment_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid)
        if not pay or pay.record_type != RecordType.PAYMENT.value:
            raise PlatformContextError("NOT_FOUND", payment_id)
        if pay.status == PaymentState.REVERSED.value:
            raise PlatformContextError("ALREADY_REVERSED", payment_id)
        # Compensating entry — do not rewrite original amounts
        rev = self.repo.create(
            record_type=RecordType.PAYMENT.value,
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            body={
                **(pay.body or {}),
                "amount_minor": -int((pay.body or {}).get("amount_minor") or 0),
                "reversal_of": pay.record_id,
                "reason": reason[:200],
                "approval_reference": appr,
            },
            status=PaymentState.RECORDED.value,
            created_by=ctx.user_id,
            reverses_id=pay.record_id,
        )
        pay = self.repo.mark_reversed(
            pay, reversed_by=rev.record_id, updated_by=ctx.user_id, audit_ref=appr,
        )
        self._ev(ctx, pay, "payment.reversed", reason or "reversed", approval=appr)
        self._audit(ctx, "hcg.payment.reversed", detail={"payment_id": payment_id, "reversal_id": rev.record_id})
        return {"payment": pay.to_public(), "reversal": rev.to_public()}

    # ── shifts / reconciliation ──────────────────────────────────────────
    def open_shift(
        self, ctx, *, opening_cash_minor: int, register_id: str = "reg-1",
        app_instance_id: str = "", idempotency_key: str = "",
    ) -> dict:
        self._human(ctx)
        self._perm(ctx, PlatformPermission.HCG_SHIFT_OPEN)
        iid = self._instance(ctx, app_instance_id)
        if not isinstance(opening_cash_minor, int) or opening_cash_minor < 0:
            raise PlatformContextError("INVALID_MONEY", "opening cash must be non-negative int")
        open_shifts = self.repo.list(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            record_type=RecordType.SHIFT.value, status=ShiftState.OPEN.value, limit=20,
        )
        for s in open_shifts:
            if (s.body or {}).get("register_id") == register_id:
                raise PlatformContextError("SHIFT_ALREADY_OPEN", s.record_id)
        if idempotency_key:
            hit = self.repo.find_idempotent(
                org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
                record_type=RecordType.SHIFT.value, idempotency_key=idempotency_key,
            )
            if hit:
                return {"shift": hit.to_public(), "idempotent_replay": True}
        rec = self.repo.create(
            record_type=RecordType.SHIFT.value,
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            body={
                "register_id": register_id,
                "cashier_id": ctx.user_id,
                "opening_cash_minor": opening_cash_minor,
                "currency": DEFAULT_CURRENCY,
                "cash_sales_minor": 0,
                "cash_expenses_minor": 0,
                "cash_withdrawals_minor": 0,
                "cash_additions_minor": 0,
            },
            status=ShiftState.OPEN.value,
            created_by=ctx.user_id,
            idempotency_key=idempotency_key,
        )
        self._ev(ctx, rec, "shift.opened", f"Opening cash {opening_cash_minor}")
        self._audit(ctx, "hcg.shift.opened", detail={"shift_id": rec.record_id})
        return {"shift": rec.to_public(), "idempotent_replay": False}

    def close_shift(
        self, ctx, shift_id: str, *, actual_cash_minor: int, explanation: str = "",
        app_instance_id: str = "",
    ) -> dict:
        self._human(ctx)
        self._perm(ctx, PlatformPermission.HCG_SHIFT_CLOSE)
        iid = self._instance(ctx, app_instance_id)
        if not isinstance(actual_cash_minor, int) or actual_cash_minor < 0:
            raise PlatformContextError("INVALID_MONEY", "actual cash must be non-negative int")
        sh = self.repo.get(shift_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid)
        if not sh or sh.record_type != RecordType.SHIFT.value:
            raise PlatformContextError("NOT_FOUND", shift_id)
        if sh.status != ShiftState.OPEN.value:
            raise PlatformContextError("SHIFT_NOT_OPEN", sh.status)

        # Expected = opening + cash sales - cash expenses - withdrawals + additions
        cash_moves = self.repo.list(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            record_type=RecordType.CASH_MOVEMENT.value, limit=500,
        )
        cash_sales = 0
        cash_exp = 0
        for m in cash_moves:
            if (m.body or {}).get("shift_id") != shift_id or m.status == "REVERSED":
                continue
            kind = (m.body or {}).get("kind")
            amt = int((m.body or {}).get("amount_minor") or 0)
            if kind == "SALE":
                cash_sales += amt
            elif kind == "EXPENSE":
                cash_exp += amt
        opening = int((sh.body or {}).get("opening_cash_minor") or 0)
        expected = opening + cash_sales - cash_exp
        diff = actual_cash_minor - expected
        if diff == 0:
            recon_status = ReconciliationStatus.BALANCED.value
        elif diff < 0:
            recon_status = ReconciliationStatus.SHORT.value
        else:
            recon_status = ReconciliationStatus.OVER.value
        if abs(diff) > 0 and not explanation:
            recon_status = ReconciliationStatus.PENDING_REVIEW.value

        recon = self.repo.create(
            record_type=RecordType.CASH_RECONCILIATION.value,
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            body={
                "shift_id": shift_id,
                "opening_cash_minor": opening,
                "cash_sales_minor": cash_sales,
                "cash_expenses_minor": cash_exp,
                "expected_cash_minor": expected,
                "actual_cash_minor": actual_cash_minor,
                "difference_minor": diff,
                "currency": DEFAULT_CURRENCY,
                "explanation": explanation[:500],
            },
            status=recon_status,
            created_by=ctx.user_id,
        )
        sh = self.repo.update_mutable(
            sh,
            status=ShiftState.CLOSED.value if recon_status != ReconciliationStatus.PENDING_REVIEW.value else ShiftState.PENDING_REVIEW.value,
            body_updates={
                "cash_sales_minor": cash_sales,
                "cash_expenses_minor": cash_exp,
                "expected_cash_minor": expected,
                "actual_cash_minor": actual_cash_minor,
                "difference_minor": diff,
                "reconciliation_id": recon.record_id,
                "explanation": explanation[:500],
            },
            updated_by=ctx.user_id,
        )
        if recon_status != ReconciliationStatus.BALANCED.value:
            self._notify(
                ctx,
                title="Cash variance",
                summary=f"Shift {shift_id} variance {diff} paisa ({recon_status})",
                event_type="hcg.cash_variance",
                related_object=shift_id,
                severity="warn",
            )
        self._ev(ctx, sh, "shift.closed", f"recon={recon_status} diff={diff}")
        self._audit(ctx, "hcg.shift.closed", detail={"shift_id": shift_id, "recon": recon_status})
        return {"shift": sh.to_public(), "reconciliation": recon.to_public()}

    def list_shifts(self, ctx, *, app_instance_id: str = "") -> dict:
        self._perm(ctx, PlatformPermission.HCG_RECONCILIATION_READ)
        iid = self._instance(ctx, app_instance_id)
        rows = self.repo.list(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            record_type=RecordType.SHIFT.value, limit=100,
        )
        return {"shifts": [r.to_public() for r in rows]}

    # ── credit / customers ───────────────────────────────────────────────
    def list_customers(self, ctx, *, app_instance_id: str = "", q: str = "") -> dict:
        self._perm(ctx, PlatformPermission.HCG_CREDIT_READ)
        iid = self._instance(ctx, app_instance_id)
        self.ensure_seeded(ctx, app_instance_id=iid)
        rows = self.repo.list(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            record_type=RecordType.CUSTOMER.value, q=q, limit=200,
        )
        return {"customers": [r.to_public() for r in rows]}

    def customer_statement(self, ctx, customer_id: str, *, app_instance_id: str = "") -> dict:
        self._perm(ctx, PlatformPermission.HCG_CREDIT_READ)
        iid = self._instance(ctx, app_instance_id)
        cust = self.repo.get(customer_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid)
        if not cust:
            raise PlatformContextError("NOT_FOUND", customer_id)
        entries = self.repo.list(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            record_type=RecordType.CREDIT_ENTRY.value, limit=500,
        )
        mine = [e for e in entries if (e.body or {}).get("customer_id") == customer_id and e.status != "REVERSED"]
        bal = sum(int((e.body or {}).get("delta_minor") or 0) for e in mine)
        return {
            "customer": cust.to_public(),
            "entries": [e.to_public() for e in mine],
            "balance_minor": bal,
            "currency": DEFAULT_CURRENCY,
            "ledger_backed": True,
        }

    def _append_credit(self, ctx, iid: str, *, customer_id: str, delta_minor: int,
                       entry_type: str, ref: str = "", note: str = "") -> Any:
        return self.repo.create(
            record_type=RecordType.CREDIT_ENTRY.value,
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            body={
                "customer_id": customer_id,
                "delta_minor": int(delta_minor),
                "currency": DEFAULT_CURRENCY,
                "entry_type": entry_type,
                "ref": ref,
                "note": note[:200],
            },
            status="RECORDED",
            created_by=ctx.user_id,
        )

    def record_repayment(
        self, ctx, *, customer_id: str, amount_minor: int, method: str = "CASH",
        shift_id: str = "", idempotency_key: str = "", app_instance_id: str = "",
    ) -> dict:
        self._human(ctx)
        self._perm(ctx, PlatformPermission.HCG_CREDIT_MANAGE)
        iid = self._instance(ctx, app_instance_id)
        try:
            money = Money.from_minor(amount_minor, DEFAULT_CURRENCY).require_positive()
        except MoneyError as e:
            raise PlatformContextError("INVALID_MONEY", str(e)) from e
        # repayment reduces debt → negative delta
        entry = self._append_credit(
            ctx, iid, customer_id=customer_id, delta_minor=-money.amount_minor,
            entry_type=CreditEntryType.REPAYMENT.value, note=f"Repayment via {method}",
        )
        if method.upper() == PaymentMethod.CASH.value and shift_id:
            self.repo.create(
                record_type=RecordType.CASH_MOVEMENT.value,
                org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
                body={
                    "kind": "REPAYMENT",
                    "amount_minor": money.amount_minor,
                    "currency": DEFAULT_CURRENCY,
                    "shift_id": shift_id,
                    "customer_id": customer_id,
                },
                status="RECORDED",
                created_by=ctx.user_id,
            )
        self._ev(ctx, entry, "credit.repayment", f"Repay {money.amount_minor}")
        self._audit(ctx, "hcg.credit.repayment", detail={"customer_id": customer_id, "amount_minor": money.amount_minor})
        return {"entry": entry.to_public()}

    def credit_correction(
        self, ctx, *, customer_id: str, delta_minor: int, reason: str,
        approval_reference: str = "", app_instance_id: str = "",
    ) -> dict:
        """Sensitive: reducing debt without repayment evidence requires approval."""
        self._human(ctx)
        self._perm(ctx, PlatformPermission.HCG_CREDIT_MANAGE)
        if delta_minor < 0:
            self._require_approval(
                ctx, action="credit.reduce_without_repayment",
                approval_reference=approval_reference, target=customer_id,
            )
        iid = self._instance(ctx, app_instance_id)
        entry = self._append_credit(
            ctx, iid, customer_id=customer_id, delta_minor=int(delta_minor),
            entry_type=CreditEntryType.CORRECTION.value, note=reason[:200],
        )
        self._ev(ctx, entry, "credit.correction", reason)
        return {"entry": entry.to_public()}

    # ── suppliers / purchases ────────────────────────────────────────────
    def list_suppliers(self, ctx, *, app_instance_id: str = "", q: str = "") -> dict:
        self._perm(ctx, PlatformPermission.HCG_SUPPLIER_READ)
        iid = self._instance(ctx, app_instance_id)
        self.ensure_seeded(ctx, app_instance_id=iid)
        rows = self.repo.list(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            record_type=RecordType.SUPPLIER.value, q=q, limit=200,
        )
        return {"suppliers": [r.to_public() for r in rows]}

    def supplier_statement(self, ctx, supplier_id: str, *, app_instance_id: str = "") -> dict:
        self._perm(ctx, PlatformPermission.HCG_SUPPLIER_READ)
        iid = self._instance(ctx, app_instance_id)
        sup = self.repo.get(supplier_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid)
        if not sup:
            raise PlatformContextError("NOT_FOUND", supplier_id)
        entries = self.repo.list(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            record_type=RecordType.SUPPLIER_ENTRY.value, limit=500,
        )
        mine = [e for e in entries if (e.body or {}).get("supplier_id") == supplier_id and e.status != "REVERSED"]
        bal = sum(int((e.body or {}).get("delta_minor") or 0) for e in mine)
        return {
            "supplier": sup.to_public(),
            "entries": [e.to_public() for e in mine],
            "balance_minor": bal,
            "currency": DEFAULT_CURRENCY,
            "ledger_backed": True,
        }

    def create_purchase(
        self, ctx, *, supplier_id: str, lines: list[dict], credit_minor: int = 0,
        paid_minor: int = 0, payment_method: str = "CASH",
        app_instance_id: str = "", idempotency_key: str = "",
    ) -> dict:
        self._human(ctx)
        self._perm(ctx, PlatformPermission.HCG_PURCHASE_MANAGE)
        iid = self._instance(ctx, app_instance_id)
        total = 0
        snap = []
        for ln in lines or []:
            qty = int(ln.get("qty") or 0)
            unit = int(ln.get("unit_price_minor") or 0)
            if qty <= 0 or unit < 0:
                raise PlatformContextError("INVALID_LINE", "qty/price invalid")
            line_total = qty * unit
            total += line_total
            snap.append({
                "inventory_item_id": ln.get("inventory_item_id") or "",
                "name": (ln.get("name") or "")[:120],
                "qty": qty,
                "unit": (ln.get("unit") or "unit")[:20],
                "unit_price_minor": unit,
                "line_total_minor": line_total,
            })
        credit_minor = int(credit_minor or 0)
        paid_minor = int(paid_minor or 0)
        if credit_minor < 0 or paid_minor < 0:
            raise PlatformContextError("INVALID_MONEY", "negative not allowed")
        if credit_minor + paid_minor != total:
            # allow unpaid remainder as credit if credit covers remainder
            if paid_minor + credit_minor < total:
                credit_minor = total - paid_minor
        pur = self.repo.create(
            record_type=RecordType.PURCHASE.value,
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            body={
                "supplier_id": supplier_id,
                "lines": snap,
                "total_minor": total,
                "paid_minor": paid_minor,
                "credit_minor": credit_minor,
                "payment_method": payment_method,
                "currency": DEFAULT_CURRENCY,
            },
            status="RECORDED",
            created_by=ctx.user_id,
            idempotency_key=idempotency_key,
        )
        # stock receipts
        for ln in snap:
            inv_id = ln.get("inventory_item_id")
            if not inv_id:
                continue
            inv = self.repo.get(inv_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid)
            if not inv:
                continue
            qty = int(ln["qty"])
            on_hand = int((inv.body or {}).get("qty_on_hand") or 0) + qty
            self.repo.update_mutable(
                inv, body_updates={"qty_on_hand": on_hand}, updated_by=ctx.user_id,
            )
            self.repo.create(
                record_type=RecordType.STOCK_MOVEMENT.value,
                org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
                body={
                    "inventory_item_id": inv_id,
                    "movement_type": StockMovementType.PURCHASE_RECEIPT.value,
                    "qty_delta": qty,
                    "ref": pur.record_id,
                    "reason": "purchase receipt",
                },
                status="RECORDED",
                created_by=ctx.user_id,
            )
        if credit_minor > 0:
            self.repo.create(
                record_type=RecordType.SUPPLIER_ENTRY.value,
                org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
                body={
                    "supplier_id": supplier_id,
                    "delta_minor": credit_minor,
                    "currency": DEFAULT_CURRENCY,
                    "entry_type": SupplierEntryType.PURCHASE.value,
                    "ref": pur.record_id,
                    "note": "Credit purchase",
                },
                status="RECORDED",
                created_by=ctx.user_id,
            )
        self._ev(ctx, pur, "purchase.created", f"Purchase {total}")
        self._audit(ctx, "hcg.purchase.created", detail={"purchase_id": pur.record_id, "total_minor": total})
        return {"purchase": pur.to_public()}

    def settle_supplier(
        self, ctx, *, supplier_id: str, amount_minor: int, method: str = "CASH",
        app_instance_id: str = "",
    ) -> dict:
        self._human(ctx)
        self._perm(ctx, PlatformPermission.HCG_SUPPLIER_MANAGE)
        iid = self._instance(ctx, app_instance_id)
        try:
            money = Money.from_minor(amount_minor, DEFAULT_CURRENCY).require_positive()
        except MoneyError as e:
            raise PlatformContextError("INVALID_MONEY", str(e)) from e
        entry = self.repo.create(
            record_type=RecordType.SUPPLIER_ENTRY.value,
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            body={
                "supplier_id": supplier_id,
                "delta_minor": -money.amount_minor,
                "currency": DEFAULT_CURRENCY,
                "entry_type": SupplierEntryType.SETTLEMENT.value,
                "note": f"Settlement via {method}",
            },
            status="RECORDED",
            created_by=ctx.user_id,
        )
        self._ev(ctx, entry, "supplier.settlement", f"Settle {money.amount_minor}")
        return {"entry": entry.to_public()}

    # ── expenses ─────────────────────────────────────────────────────────
    def create_expense(
        self, ctx, *, category: str, amount_minor: int, description: str = "",
        payment_source: str = "CASH", shift_id: str = "",
        app_instance_id: str = "", idempotency_key: str = "",
    ) -> dict:
        self._human(ctx)
        self._perm(ctx, PlatformPermission.HCG_EXPENSE_MANAGE)
        iid = self._instance(ctx, app_instance_id)
        try:
            money = Money.from_minor(amount_minor, DEFAULT_CURRENCY).require_positive()
        except MoneyError as e:
            raise PlatformContextError("INVALID_MONEY", str(e)) from e
        rec = self.repo.create(
            record_type=RecordType.EXPENSE.value,
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            body={
                "category": category[:80],
                "amount_minor": money.amount_minor,
                "currency": DEFAULT_CURRENCY,
                "description": description[:500],
                "payment_source": payment_source[:40],
                "shift_id": shift_id,
            },
            status="RECORDED",
            created_by=ctx.user_id,
            idempotency_key=idempotency_key,
        )
        if payment_source.upper() == "CASH" and shift_id:
            self.repo.create(
                record_type=RecordType.CASH_MOVEMENT.value,
                org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
                body={
                    "kind": "EXPENSE",
                    "amount_minor": money.amount_minor,
                    "currency": DEFAULT_CURRENCY,
                    "shift_id": shift_id,
                    "expense_id": rec.record_id,
                },
                status="RECORDED",
                created_by=ctx.user_id,
            )
        self._ev(ctx, rec, "expense.created", description or category)
        self._audit(ctx, "hcg.expense.created", detail={"expense_id": rec.record_id})
        return {"expense": rec.to_public()}

    def list_expenses(self, ctx, *, app_instance_id: str = "") -> dict:
        self._perm(ctx, PlatformPermission.HCG_EXPENSE_READ)
        iid = self._instance(ctx, app_instance_id)
        rows = self.repo.list(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            record_type=RecordType.EXPENSE.value, limit=200,
        )
        return {"expenses": [r.to_public() for r in rows]}

    # ── inventory ────────────────────────────────────────────────────────
    def list_inventory(self, ctx, *, app_instance_id: str = "", q: str = "") -> dict:
        self._perm(ctx, PlatformPermission.HCG_INVENTORY_READ)
        iid = self._instance(ctx, app_instance_id)
        self.ensure_seeded(ctx, app_instance_id=iid)
        rows = self.repo.list(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            record_type=RecordType.INVENTORY_ITEM.value, q=q, limit=200,
        )
        return {"items": [r.to_public() for r in rows]}

    def stock_adjust(
        self, ctx, *, inventory_item_id: str, qty_delta: int, reason: str,
        movement_type: str = StockMovementType.ADJUSTMENT_IN.value,
        approval_reference: str = "", app_instance_id: str = "",
    ) -> dict:
        self._human(ctx)
        self._perm(ctx, PlatformPermission.HCG_INVENTORY_MANAGE)
        iid = self._instance(ctx, app_instance_id)
        inv = self.repo.get(
            inventory_item_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
        )
        if not inv:
            raise PlatformContextError("NOT_FOUND", inventory_item_id)
        on_hand = int((inv.body or {}).get("qty_on_hand") or 0) + int(qty_delta)
        if on_hand < 0:
            raise PlatformContextError("STOCK_UNDERFLOW", "qty would be negative")
        if abs(int(qty_delta)) >= 100:
            self._require_approval(
                ctx, action="inventory.large_adjustment",
                approval_reference=approval_reference, target=inventory_item_id,
            )
        inv = self.repo.update_mutable(
            inv, body_updates={"qty_on_hand": on_hand}, updated_by=ctx.user_id,
        )
        mov = self.repo.create(
            record_type=RecordType.STOCK_MOVEMENT.value,
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            body={
                "inventory_item_id": inventory_item_id,
                "movement_type": movement_type,
                "qty_delta": int(qty_delta),
                "reason": reason[:200],
            },
            status="RECORDED",
            created_by=ctx.user_id,
        )
        min_q = int((inv.body or {}).get("min_qty") or 0)
        if on_hand <= min_q:
            alert = self.repo.create(
                record_type=RecordType.ALERT.value,
                org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
                body={
                    "kind": "LOW_STOCK",
                    "inventory_item_id": inventory_item_id,
                    "name": (inv.body or {}).get("name"),
                    "qty_on_hand": on_hand,
                    "min_qty": min_q,
                },
                status="OPEN",
                created_by=ctx.user_id,
                idempotency_key=f"lowstock:{inventory_item_id}:{on_hand}",
            )
            self._notify(
                ctx,
                title="Low stock",
                summary=f"{(inv.body or {}).get('name')} at {on_hand} (min {min_q})",
                event_type="hcg.low_stock",
                related_object=inventory_item_id,
                severity="warn",
                dedupe_key=f"lowstock:{inventory_item_id}",
            )
            self._ev(ctx, alert, "alert.low_stock", "Low stock")
        self._ev(ctx, mov, "stock.adjusted", reason)
        return {"item": inv.to_public(), "movement": mov.to_public()}

    def _consume_for_order(self, ctx, iid: str, order) -> None:
        meta = self.repo.list(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            record_type=RecordType.META.value, limit=1,
        )
        mode = "automatic"
        if meta:
            mode = (meta[0].body or {}).get("consumption_mode") or "automatic"
        if mode != "automatic":
            return
        recipes = {
            r.record_id: r
            for r in self.repo.list(
                org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
                record_type=RecordType.RECIPE.value, limit=200,
            )
        }
        menu = {
            m.record_id: m
            for m in self.repo.list(
                org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
                record_type=RecordType.MENU_ITEM.value, limit=200,
            )
        }
        for ln in (order.body or {}).get("lines") or []:
            mid = ln.get("menu_item_id")
            mi = menu.get(mid)
            if not mi:
                continue
            rid = (mi.body or {}).get("recipe_id")
            recipe = recipes.get(rid) if rid else None
            if not recipe:
                continue
            for ing in (recipe.body or {}).get("ingredients") or []:
                inv_id = ing.get("inventory_item_id")
                qty_each = int(ing.get("qty") or 0)
                use = qty_each * int(ln.get("qty") or 0)
                if not inv_id or use <= 0:
                    continue
                inv = self.repo.get(inv_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid)
                if not inv:
                    continue
                on_hand = max(0, int((inv.body or {}).get("qty_on_hand") or 0) - use)
                self.repo.update_mutable(inv, body_updates={"qty_on_hand": on_hand}, updated_by=ctx.user_id)
                self.repo.create(
                    record_type=RecordType.STOCK_MOVEMENT.value,
                    org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
                    body={
                        "inventory_item_id": inv_id,
                        "movement_type": StockMovementType.SALE_CONSUMPTION.value,
                        "qty_delta": -use,
                        "ref": order.record_id,
                        "reason": "recipe consumption",
                    },
                    status="RECORDED",
                    created_by=ctx.user_id,
                )

    # ── reports / search ─────────────────────────────────────────────────
    def report(self, ctx, *, kind: str = "daily_sales", app_instance_id: str = "") -> dict:
        self._perm(ctx, PlatformPermission.HCG_REPORT_READ)
        iid = self._instance(ctx, app_instance_id)
        dash = self.dashboard(ctx, app_instance_id=iid)
        payments = self.repo.list(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            record_type=RecordType.PAYMENT.value, limit=500,
        )
        by_method: dict[str, int] = {}
        for p in payments:
            if p.status == PaymentState.REVERSED.value:
                continue
            m = (p.body or {}).get("method") or "UNKNOWN"
            by_method[m] = by_method.get(m, 0) + int((p.body or {}).get("amount_minor") or 0)
        item_sales: dict[str, dict] = {}
        for o in self.repo.list(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            record_type=RecordType.ORDER.value, limit=500,
        ):
            if o.status in (OrderState.CANCELLED.value, OrderState.REVERSED.value, OrderState.DRAFT.value):
                continue
            for ln in (o.body or {}).get("lines") or []:
                name = ln.get("name") or "item"
                slot = item_sales.setdefault(name, {"name": name, "qty": 0, "sales_minor": 0})
                slot["qty"] += int(ln.get("qty") or 0)
                slot["sales_minor"] += int(ln.get("qty") or 0) * int(ln.get("unit_price_minor") or 0)
        snap = {
            "kind": kind,
            "metrics": dash["metrics"],
            "payment_methods": by_method,
            "item_sales": sorted(item_sales.values(), key=lambda x: -x["sales_minor"])[:50],
            "currency": DEFAULT_CURRENCY,
            "label": "demo/certification data",
            "derived_from_authoritative_records": True,
        }
        rec = self.repo.create(
            record_type=RecordType.REPORT_SNAPSHOT.value,
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            body=snap,
            status="READY",
            created_by=ctx.user_id,
        )
        return {"report": rec.to_public(), "data": snap}

    def search(self, ctx, *, q: str, types: list[str] | None = None,
               app_instance_id: str = "", limit: int = 50) -> dict:
        self._perm(ctx, PlatformPermission.HCG_DASHBOARD_READ)
        iid = self._instance(ctx, app_instance_id)
        q = (q or "").strip()[:80]
        if not q:
            return {"results": [], "count": 0}
        type_list = types or [
            RecordType.ORDER.value, RecordType.CUSTOMER.value, RecordType.SUPPLIER.value,
            RecordType.MENU_ITEM.value, RecordType.PAYMENT.value, RecordType.EXPENSE.value,
            RecordType.INVENTORY_ITEM.value, RecordType.PURCHASE.value, RecordType.SHIFT.value,
        ]
        results = []
        for rt in type_list[:12]:
            rows = self.repo.list(
                org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
                record_type=rt, q=q, limit=min(limit, 20),
            )
            for r in rows:
                results.append(r.to_public())
            if len(results) >= limit:
                break
        return {"results": results[:limit], "count": len(results[:limit]), "q": q}

    def list_notifications(self, ctx, *, limit: int = 50) -> dict:
        self._perm(ctx, PlatformPermission.NOTIFICATION_READ)
        # Reuse platform notifications for workspace
        try:
            rows = self.store.list_notifications(
                org_id=ctx.org_id, workspace_id=ctx.workspace_id, limit=limit,
            )
        except Exception:
            rows = []
        return {"notifications": rows if isinstance(rows, list) else []}

    # ── grounded Q&A (Conversation / Yeti — read only) ───────────────────
    def grounded_answer(self, ctx, question: str, *, app_instance_id: str = "") -> dict:
        """Read-only operational answers. Never mutates financial records."""
        self._perm(ctx, PlatformPermission.HCG_DASHBOARD_READ)
        iid = self._instance(ctx, app_instance_id)
        q = (question or "").lower()
        dash = self.dashboard(ctx, app_instance_id=iid)
        m = dash["metrics"]
        facts = []
        answer = ""
        if "sales" in q and ("today" in q or "day" in q):
            answer = f"Today's sales are {m['sales_today_minor']} paisa ({DEFAULT_CURRENCY}) across {m['order_count']} orders."
            facts.append({"metric": "sales_today_minor", "value": m["sales_today_minor"]})
        elif "cash" in q and ("register" or "should") in q:
            shifts = dash.get("open_shifts") or []
            if shifts:
                s = shifts[0]
                body = s.get("body") or {}
                answer = (
                    f"Open shift {s.get('record_id')} opening cash "
                    f"{body.get('opening_cash_minor', 0)} paisa; cash received today "
                    f"{m['cash_received_minor']} paisa."
                )
            else:
                answer = "No open cashier shift. Cash received today: " + str(m["cash_received_minor"]) + " paisa."
            facts.append({"metric": "cash_received_minor", "value": m["cash_received_minor"]})
        elif "overdue" in q or ("credit" in q and "customer" in q) or "owe" in q:
            answer = f"Customer credit outstanding: {m['customer_credit_outstanding_minor']} paisa (ledger-backed)."
            facts.append({"metric": "customer_credit_outstanding_minor", "value": m["customer_credit_outstanding_minor"]})
        elif "supplier" in q:
            answer = f"Supplier dues outstanding: {m['supplier_dues_minor']} paisa (ledger-backed)."
            facts.append({"metric": "supplier_dues_minor", "value": m["supplier_dues_minor"]})
        elif "low stock" in q or "stock" in q:
            answer = f"{m['low_stock_count']} items at or below minimum stock."
            facts.append({"metric": "low_stock_count", "value": m["low_stock_count"]})
            facts.extend([{"item": x.get("body", {}).get("name"), "qty": x.get("body", {}).get("qty_on_hand")} for x in dash.get("low_stock") or []])
        elif "kitchen" in q:
            answer = f"{m['active_kitchen_tickets']} active kitchen tickets."
            facts.append({"metric": "active_kitchen_tickets", "value": m["active_kitchen_tickets"]})
        elif "expense" in q:
            answer = f"Expenses total {m['expenses_minor']} paisa."
            facts.append({"metric": "expenses_minor", "value": m["expenses_minor"]})
        else:
            answer = (
                f"HCG snapshot — sales {m['sales_today_minor']} paisa, "
                f"orders {m['order_count']}, open shifts {m['open_shift_count']}."
            )
            facts.append({"metrics": m})
        return {
            "answer": answer,
            "facts": facts,
            "estimates": False,
            "mutable": False,
            "label": "demo/certification data",
            "source": "HcgService.grounded_answer",
            "rbac_enforced": True,
            "can_mutate": False,
        }

    def propose_action(self, ctx, *, action: str, payload: dict | None = None) -> dict:
        """Conversation may propose actions; never execute financial mutations."""
        self._perm(ctx, PlatformPermission.HCG_DASHBOARD_READ)
        return {
            "proposal": {
                "action": action,
                "payload": payload or {},
                "requires_confirmation": True,
                "requires_human_operator": True,
                "executed": False,
            },
            "note": "Yeti/Conversation cannot mutate HCG financial records directly.",
        }

    # ── backup / restore (coordinates with AppRuntime) ───────────────────
    def export_backup_payload(self, ctx, *, app_instance_id: str = "") -> dict:
        self._perm(ctx, PlatformPermission.HCG_BACKUP_MANAGE)
        iid = self._instance(ctx, app_instance_id)
        data = self.repo.export_scope(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
        )
        blob = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        digest = hashlib.sha256(blob).hexdigest()
        payload = {
            "schema_version": SCHEMA_VERSION,
            "app_id": APP_ID,
            "app_instance_id": iid,
            "org_id": ctx.org_id,
            "workspace_id": ctx.workspace_id,
            "content_hash": digest,
            "record_count": data["record_count"],
            "evidence_count": data["evidence_count"],
            "data": data,
            "created_by": ctx.user_id,
            "created_at": self.store._now(),
            "production": False,
        }
        self._audit(ctx, "hcg.backup.exported", detail={"hash": digest, "records": data["record_count"]})
        return payload

    def restore_payload(
        self, ctx, payload: dict, *, approval_reference: str = "", app_instance_id: str = "",
    ) -> dict:
        self._human(ctx)
        self._perm(ctx, PlatformPermission.HCG_RESTORE_MANAGE)
        self._require_approval(
            ctx, action="restore.overwrite", approval_reference=approval_reference,
        )
        iid = self._instance(ctx, app_instance_id)
        if payload.get("org_id") and payload["org_id"] != ctx.org_id:
            raise PlatformContextError("RESTORE_SCOPE", "org mismatch")
        if payload.get("workspace_id") and payload["workspace_id"] != ctx.workspace_id:
            raise PlatformContextError("RESTORE_SCOPE", "workspace mismatch")
        if payload.get("schema_version") and payload["schema_version"] != SCHEMA_VERSION:
            # allow only exact schema for this mission
            raise PlatformContextError("SCHEMA_MISMATCH", payload.get("schema_version") or "")
        data = payload.get("data") or {}
        # integrity
        blob = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        digest = hashlib.sha256(blob).hexdigest()
        if payload.get("content_hash") and payload["content_hash"] != digest:
            raise PlatformContextError("INTEGRITY_MISMATCH", "content hash mismatch")
        # pre-restore checkpoint
        checkpoint = self.repo.export_scope(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
        )
        counts = self.repo.replace_scope(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid, payload=data,
        )
        self._audit(
            ctx, "hcg.restore.applied",
            detail={"records": counts["records"], "approval": approval_reference, "hash": digest},
        )
        return {
            "restored": counts,
            "checkpoint_records": checkpoint.get("record_count", 0),
            "content_hash": digest,
            "evidence_preserved": True,
        }

    def safe_csv_export(self, ctx, *, kind: str = "payments", app_instance_id: str = "") -> dict:
        """Bounded CSV with formula-injection hardening."""
        self._perm(ctx, PlatformPermission.HCG_REPORT_EXPORT)
        iid = self._instance(ctx, app_instance_id)
        rows = self.repo.list(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, app_instance_id=iid,
            record_type=kind if kind in {t.value for t in RecordType} else RecordType.PAYMENT.value,
            limit=200,
        )
        lines = ["record_id,status,amount_or_name,created_at"]
        for r in rows:
            body = r.body or {}
            val = body.get("amount_minor", body.get("name", body.get("token", "")))
            cell = _csv_safe(str(val))
            lines.append(f"{_csv_safe(r.record_id)},{_csv_safe(r.status)},{cell},{r.created_at}")
        return {"csv": "\n".join(lines), "count": len(rows), "kind": kind}


_CSV_DANGEROUS = re.compile(r"^[=+\-@]")


def _csv_safe(value: str) -> str:
    s = value.replace('"', '""')
    if _CSV_DANGEROUS.match(s) or s.startswith("\t"):
        s = "'" + s
    return f'"{s}"'


# Singleton helpers
_DEFAULT: HcgService | None = None


def default_hcg_service(platform_service=None) -> HcgService:
    global _DEFAULT
    if platform_service is not None:
        existing = getattr(platform_service, "_hcg_service", None)
        if existing is not None:
            return existing
        svc = HcgService(platform_service.store, platform=platform_service)
        setattr(platform_service, "_hcg_service", svc)
        return svc
    if _DEFAULT is None:
        from saathi.platform.service import default_platform

        p = default_platform()
        _DEFAULT = HcgService(p.store, platform=p)
    return _DEFAULT


def reset_hcg_service_for_tests(platform_service=None) -> None:
    global _DEFAULT
    _DEFAULT = None
    if platform_service is not None and hasattr(platform_service, "_hcg_service"):
        delattr(platform_service, "_hcg_service")
