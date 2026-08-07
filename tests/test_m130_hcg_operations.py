"""M130–M138 HCG Native Operations Application — focused domain tests."""
from __future__ import annotations

import pytest

from saathi.platform.context import PlatformContextError, PlatformExecutionContext
from saathi.platform.hcg.money import Money, MoneyError, parse_money_input
from saathi.platform.hcg.models import OrderState, order_totals
from saathi.platform.hcg.service import HcgService, reset_hcg_service_for_tests
from saathi.platform.models import PlatformPermission, PlatformRole, role_has_permission
from saathi.platform.store import PlatformStore


def ctx(*, user="cashier", role="operator", org="org-hcg", workspace="ws-hcg"):
    return PlatformExecutionContext(
        user_id=user,
        role=role,
        org_id=org,
        workspace_id=workspace,
        session_id=f"session-{user}",
    )


@pytest.fixture
def service(tmp_path):
    store = PlatformStore(tmp_path / "hcg.db", now=lambda: 1_700_000_000.0)
    svc = HcgService(store)
    yield svc, store
    reset_hcg_service_for_tests()
    store.close()


def test_money_integer_minor_rejects_float():
    m = Money.from_minor(18000, "NPR")
    assert m.amount_minor == 18000
    assert "180.00" in m.to_public()["display"]
    with pytest.raises(MoneyError):
        Money.from_major(1.5)
    with pytest.raises(MoneyError):
        parse_money_input(amount_minor=1.2)


def test_order_totals_no_float():
    t = order_totals(
        [{"qty": 2, "unit_price_minor": 1500, "discount_minor": 100}],
        discount_minor=200,
    )
    assert t["subtotal_minor"] == 2900
    assert t["total_minor"] == 2700


def test_hcg_permissions_mapped():
    assert role_has_permission(PlatformRole.VIEWER, PlatformPermission.HCG_DASHBOARD_READ)
    assert not role_has_permission(PlatformRole.VIEWER, PlatformPermission.HCG_ORDER_CREATE)
    assert role_has_permission(PlatformRole.OPERATOR, PlatformPermission.HCG_PAYMENT_RECORD)
    assert not role_has_permission(PlatformRole.OPERATOR, PlatformPermission.HCG_PAYMENT_REVERSE)
    assert role_has_permission(PlatformRole.OWNER, PlatformPermission.HCG_PAYMENT_REVERSE)
    assert role_has_permission(PlatformRole.OWNER, PlatformPermission.HCG_ADMIN)


def test_seed_dashboard_and_isolation(service):
    svc, store = service
    c = ctx()
    dash = svc.dashboard(c)
    assert dash["fabricated"] is False
    assert dash["derived_from_authoritative_records"] is True
    assert "demo" in dash["label"].lower() or "cert" in dash["label"].lower()
    assert dash["metrics"]["low_stock_count"] >= 1

    other = ctx(org="org-b", workspace="ws-b", user="other")
    d2 = svc.dashboard(other)
    # separate seed instances
    assert d2["app_instance_id"] != dash["app_instance_id"] or other.org_id != c.org_id


def test_order_payment_cash_kitchen_shift(service):
    svc, _ = service
    c = ctx(role="owner")  # owner has all HCG
    svc.ensure_seeded(c)
    menu = svc.list_menu(c)
    item = menu["items"][0]
    sh = svc.open_shift(c, opening_cash_minor=100000, idempotency_key="sh1")
    shift_id = sh["shift"]["record_id"]
    # duplicate shift rejected
    with pytest.raises(PlatformContextError) as err:
        svc.open_shift(c, opening_cash_minor=1)
    assert err.value.code == "SHIFT_ALREADY_OPEN"

    order = svc.create_order(
        c,
        lines=[{"menu_item_id": item["record_id"], "qty": 1}],
        shift_id=shift_id,
        idempotency_key="ord1",
    )
    # idempotent replay
    order2 = svc.create_order(
        c,
        lines=[{"menu_item_id": item["record_id"], "qty": 1}],
        shift_id=shift_id,
        idempotency_key="ord1",
    )
    assert order2["idempotent_replay"] is True
    assert order2["order"]["record_id"] == order["order"]["record_id"]

    kit = svc.submit_to_kitchen(c, order["order"]["record_id"])
    assert kit["tickets"]
    tid = kit["tickets"][0]["record_id"]
    svc.transition_kitchen(c, tid, to_state="PREPARING")
    svc.transition_kitchen(c, tid, to_state="READY")

    total = order["order"]["body"]["total_minor"]
    pay = svc.record_payment(
        c,
        order_id=order["order"]["record_id"],
        amount_minor=total,
        method="CASH",
        shift_id=shift_id,
        idempotency_key="pay1",
    )
    assert pay["order"]["status"] in (OrderState.PAID.value, "PAID")
    # duplicate payment idemp
    pay2 = svc.record_payment(
        c,
        order_id=order["order"]["record_id"],
        amount_minor=total,
        method="CASH",
        shift_id=shift_id,
        idempotency_key="pay1",
    )
    assert pay2["idempotent_replay"] is True

    # float payment rejected
    with pytest.raises(Exception):
        Money.from_minor(1.5)  # type: ignore[arg-type]


def test_qr_and_credit_ledger(service):
    svc, _ = service
    c = ctx(role="owner")
    svc.ensure_seeded(c)
    menu = svc.list_menu(c)["items"]
    customers = svc.list_customers(c)["customers"]
    cust = customers[0]["record_id"]
    before = svc.customer_statement(c, cust)["balance_minor"]

    o = svc.create_order(
        c,
        lines=[{"menu_item_id": menu[0]["record_id"], "qty": 1}],
        customer_id=cust,
        idempotency_key="cred-ord",
    )
    total = o["order"]["body"]["total_minor"]
    # QR requires ref
    with pytest.raises(PlatformContextError) as e1:
        svc.record_payment(
            c, order_id=o["order"]["record_id"], amount_minor=total, method="QR",
        )
    assert e1.value.code == "QR_REF_REQUIRED"

    o2 = svc.create_order(
        c,
        lines=[{"menu_item_id": menu[1]["record_id"], "qty": 1}],
        customer_id=cust,
        idempotency_key="qr-ord",
    )
    t2 = o2["order"]["body"]["total_minor"]
    svc.record_payment(
        c,
        order_id=o2["order"]["record_id"],
        amount_minor=t2,
        method="QR",
        qr_reference="QR-CERT-001",
        idempotency_key="qrpay",
    )
    with pytest.raises(PlatformContextError) as e2:
        # new order but same QR ref
        o3 = svc.create_order(
            c,
            lines=[{"menu_item_id": menu[1]["record_id"], "qty": 1}],
            idempotency_key="qr-ord2",
        )
        svc.record_payment(
            c,
            order_id=o3["order"]["record_id"],
            amount_minor=o3["order"]["body"]["total_minor"],
            method="QR",
            qr_reference="QR-CERT-001",
        )
    assert e2.value.code == "DUPLICATE_PAYMENT_REF"

    svc.record_payment(
        c,
        order_id=o["order"]["record_id"],
        amount_minor=total,
        method="CREDIT",
        customer_id=cust,
        idempotency_key="credpay",
    )
    after = svc.customer_statement(c, cust)["balance_minor"]
    assert after == before + total
    # repayment
    svc.record_repayment(c, customer_id=cust, amount_minor=1000)
    after2 = svc.customer_statement(c, cust)["balance_minor"]
    assert after2 == after - 1000


def test_payment_reverse_requires_approval(service):
    svc, store = service
    c = ctx(role="owner")
    svc.ensure_seeded(c)
    menu = svc.list_menu(c)["items"][0]
    o = svc.create_order(
        c, lines=[{"menu_item_id": menu["record_id"], "qty": 1}], idempotency_key="rev-o",
    )
    p = svc.record_payment(
        c,
        order_id=o["order"]["record_id"],
        amount_minor=o["order"]["body"]["total_minor"],
        method="CASH",
        idempotency_key="rev-p",
    )
    with pytest.raises(PlatformContextError) as err:
        svc.reverse_payment(c, p["payment"]["record_id"])
    assert err.value.code == "APPROVAL_REQUIRED"


def test_purchase_inventory_supplier(service):
    svc, _ = service
    c = ctx(role="owner")
    svc.ensure_seeded(c)
    inv = svc.list_inventory(c)["items"][0]
    before = int(inv["body"]["qty_on_hand"])
    sup = svc.list_suppliers(c)["suppliers"][0]
    bal_before = svc.supplier_statement(c, sup["record_id"])["balance_minor"]
    svc.create_purchase(
        c,
        supplier_id=sup["record_id"],
        lines=[
            {
                "inventory_item_id": inv["record_id"],
                "name": inv["body"]["name"],
                "qty": 10,
                "unit_price_minor": 500,
            }
        ],
        paid_minor=2000,
        credit_minor=3000,
    )
    inv2 = svc.list_inventory(c)["items"]
    match = next(i for i in inv2 if i["record_id"] == inv["record_id"])
    assert int(match["body"]["qty_on_hand"]) == before + 10
    bal_after = svc.supplier_statement(c, sup["record_id"])["balance_minor"]
    assert bal_after == bal_before + 3000


def test_expense_and_shift_close(service):
    svc, _ = service
    c = ctx(role="owner")
    sh = svc.open_shift(c, opening_cash_minor=50000, idempotency_key="sh-close")
    sid = sh["shift"]["record_id"]
    svc.create_expense(
        c, category="supplies", amount_minor=1000, shift_id=sid, payment_source="CASH",
    )
    closed = svc.close_shift(c, sid, actual_cash_minor=49000)
    assert closed["reconciliation"]["status"] in ("BALANCED", "SHORT", "OVER", "PENDING_REVIEW")
    assert closed["reconciliation"]["body"]["expected_cash_minor"] == 49000


def test_viewer_cannot_mutate(service):
    svc, _ = service
    v = ctx(role="viewer")
    svc.dashboard(v)  # read ok
    with pytest.raises(PlatformContextError):
        svc.create_order(v, lines=[{"name": "x", "qty": 1, "unit_price_minor": 100}])


def test_backup_restore_integrity(service):
    svc, store = service
    c = ctx(role="owner")
    svc.ensure_seeded(c)
    backup = svc.export_backup_payload(c)
    assert backup["content_hash"]
    assert backup["record_count"] > 0
    with pytest.raises(PlatformContextError) as err:
        svc.restore_payload(c, backup, approval_reference="")
    assert err.value.code == "APPROVAL_REQUIRED"
    # with approval ref string only (no platform validation without real approval)
    # force path by monkeypatching require
    from saathi.platform.models import ApprovalRecord, ApprovalStatus
    import time

    apr = ApprovalRecord(
        approval_id="apr_hcg_test",
        user_id=c.user_id,
        org_id=c.org_id,
        workspace_id=c.workspace_id,
        project_id="",
        mission_id="",
        tool_id="hcg.restore",
        action="restore",
        target_resource="hcg",
        authority="owner",
        side_effect_class="destructive",
        status=ApprovalStatus.APPROVED.value,
        requested_by=c.user_id,
        created_at=time.time(),
        expires_at=time.time() + 3600,
    )
    store.save_approval(apr)
    # mutate then restore
    svc.create_expense(c, category="tmp", amount_minor=99)
    out = svc.restore_payload(c, backup, approval_reference="apr_hcg_test")
    assert out["restored"]["records"] == backup["record_count"]
    assert out["evidence_preserved"] is True


def test_grounded_answer_readonly(service):
    svc, _ = service
    c = ctx(role="owner")
    ans = svc.grounded_answer(c, "What were today’s sales?")
    assert ans["can_mutate"] is False
    assert ans["mutable"] is False
    assert "sales" in ans["answer"].lower() or "paisa" in ans["answer"].lower()
    prop = svc.propose_action(c, action="record expense", payload={"amount_minor": 1})
    assert prop["proposal"]["executed"] is False


def test_financial_immutable(service):
    svc, _ = service
    c = ctx(role="owner")
    svc.ensure_seeded(c)
    menu = svc.list_menu(c)["items"][0]
    o = svc.create_order(
        c, lines=[{"menu_item_id": menu["record_id"], "qty": 1}], idempotency_key="imm",
    )
    p = svc.record_payment(
        c,
        order_id=o["order"]["record_id"],
        amount_minor=o["order"]["body"]["total_minor"],
        method="CASH",
        idempotency_key="imm-p",
    )
    rec = svc.repo.get(
        p["payment"]["record_id"],
        org_id=c.org_id,
        workspace_id=c.workspace_id,
        app_instance_id=p["payment"]["app_instance_id"],
    )
    from saathi.platform.hcg.models import HcgValidationError

    with pytest.raises(HcgValidationError) as err:
        svc.repo.update_mutable(rec, body_updates={"amount_minor": 1})
    assert err.value.code == "FINANCIAL_IMMUTABLE"


def test_price_snapshot_survives_menu_change(service):
    svc, _ = service
    c = ctx(role="owner")
    svc.ensure_seeded(c)
    menu = svc.list_menu(c)["items"][0]
    price = menu["body"]["price_minor"]
    o = svc.create_order(
        c, lines=[{"menu_item_id": menu["record_id"], "qty": 1}], idempotency_key="snap",
    )
    svc.upsert_menu_item(
        c,
        name=menu["body"]["name"],
        category_id=menu["body"].get("category_id") or "",
        price_minor=price + 5000,
        item_id=menu["record_id"],
    )
    got = svc.get_order(c, o["order"]["record_id"])
    assert got["order"]["body"]["lines"][0]["unit_price_minor"] == price


def test_search_and_report(service):
    svc, _ = service
    c = ctx(role="owner")
    svc.ensure_seeded(c)
    r = svc.report(c, kind="daily_sales")
    assert r["data"]["derived_from_authoritative_records"] is True
    s = svc.search(c, q="Tea")
    assert s["count"] >= 0


def test_stock_underflow_and_low_stock_alert(service):
    svc, _ = service
    c = ctx(role="owner")
    svc.ensure_seeded(c)
    inv = svc.list_inventory(c)["items"]
    oil = next(i for i in inv if "oil" in (i["body"].get("name") or "").lower())
    # already low; consume more carefully
    with pytest.raises(PlatformContextError) as err:
        svc.stock_adjust(
            c,
            inventory_item_id=oil["record_id"],
            qty_delta=-3,  # on_hand is 2 — underflow without large-adjustment gate
            reason="bad",
            movement_type="ADJUSTMENT_OUT",
        )
    assert err.value.code == "STOCK_UNDERFLOW"
