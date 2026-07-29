"""Deterministic synthetic HCG seed data for local certification.

Never copies live HCG customer or financial data.
"""
from __future__ import annotations

from typing import Any

from .models import RecordType


def build_seed_payload() -> list[dict[str, Any]]:
    """Return create specs for demo/certification records."""
    loc = "loc-hcg-main"
    items: list[dict[str, Any]] = []

    items.append({
        "record_type": RecordType.LOCATION.value,
        "location_id": loc,
        "status": "ACTIVE",
        "idempotency_key": "seed:location:main",
        "body": {
            "name": "HCG Cafeteria (Demo)",
            "code": "HCG-MAIN",
            "timezone": "Asia/Kathmandu",
            "label": "demo/certification",
        },
    })
    items.append({
        "record_type": RecordType.REGISTER.value,
        "location_id": loc,
        "status": "ACTIVE",
        "idempotency_key": "seed:register:1",
        "body": {"register_id": "reg-1", "name": "Front Counter", "location_id": loc},
    })

    # Categories
    cat_meals = "cat-meals"
    cat_drinks = "cat-drinks"
    cat_snacks = "cat-snacks"
    for cid, name in ((cat_meals, "Meals"), (cat_drinks, "Drinks"), (cat_snacks, "Snacks")):
        items.append({
            "record_type": RecordType.MENU_CATEGORY.value,
            "location_id": loc,
            "status": "ACTIVE",
            "idempotency_key": f"seed:cat:{cid}",
            "body": {"category_id": cid, "name": name, "sort": 1},
        })

    # Inventory
    inv_rice = "inv-rice"
    inv_dal = "inv-dal"
    inv_tea = "inv-tea"
    inv_oil = "inv-oil"  # low stock
    for iid, name, qty, min_q, unit in (
        (inv_rice, "Rice (kg)", 50, 10, "kg"),
        (inv_dal, "Dal (kg)", 30, 5, "kg"),
        (inv_tea, "Tea leaves (g)", 2000, 200, "g"),
        (inv_oil, "Cooking oil (L)", 2, 5, "L"),  # low stock for alerts
    ):
        items.append({
            "record_type": RecordType.INVENTORY_ITEM.value,
            "location_id": loc,
            "status": "ACTIVE",
            "idempotency_key": f"seed:inv:{iid}",
            "body": {
                "inventory_item_id": iid,
                "name": name,
                "qty_on_hand": qty,
                "min_qty": min_q,
                "unit": unit,
                "label": "demo/certification",
            },
        })

    # Recipe for dal bhat
    recipe_dalbhat = "recipe-dalbhat"
    items.append({
        "record_type": RecordType.RECIPE.value,
        "status": "ACTIVE",
        "idempotency_key": f"seed:recipe:{recipe_dalbhat}",
        "body": {
            "name": "Dal Bhat",
            "ingredients": [
                {"inventory_item_id": inv_rice, "qty": 1, "unit": "kg"},
                {"inventory_item_id": inv_dal, "qty": 1, "unit": "kg"},
            ],
        },
    })

    # Menu items (prices in paisa)
    menu = [
        ("menu-dalbhat", "Dal Bhat Set", cat_meals, 18000, recipe_dalbhat, True),
        ("menu-momo", "Chicken Momo (10pc)", cat_meals, 15000, "", True),
        ("menu-chowmein", "Chowmein", cat_meals, 12000, "", False),
        ("menu-tea", "Milk Tea", cat_drinks, 3000, "", True),
        ("menu-coffee", "Coffee", cat_drinks, 5000, "", False),
        ("menu-samosa", "Samosa", cat_snacks, 2500, "", True),
    ]
    for mid, name, cat, price, recipe, fav in menu:
        items.append({
            "record_type": RecordType.MENU_ITEM.value,
            "location_id": loc,
            "status": "ACTIVE",
            "idempotency_key": f"seed:menu:{mid}",
            "body": {
                "menu_item_id": mid,
                "name": name,
                "category_id": cat,
                "price_minor": price,
                "currency": "NPR",
                "available": True,
                "favorite": fav,
                "recipe_id": recipe,
                "station": "main",
                "label": "demo/certification",
            },
        })

    # Customers
    cust_a = "cust-ram"
    cust_b = "cust-sita"
    for cid, name, phone in (
        (cust_a, "Ram Sharma (Demo)", "9800000001"),
        (cust_b, "Sita Thapa (Demo)", "9800000002"),
    ):
        items.append({
            "record_type": RecordType.CUSTOMER.value,
            "status": "ACTIVE",
            "idempotency_key": f"seed:cust:{cid}",
            "body": {
                "customer_id": cid,
                "name": name,
                "phone": phone,
                "label": "demo/certification — not a real patient record",
            },
        })

    # Opening credit entry for Ram
    items.append({
        "record_type": RecordType.CREDIT_ENTRY.value,
        "status": "RECORDED",
        "idempotency_key": "seed:credit:opening:ram",
        "body": {
            "customer_id": cust_a,
            "delta_minor": 50000,  # 500 NPR outstanding demo
            "currency": "NPR",
            "entry_type": "OPENING",
            "note": "Demo opening balance",
        },
    })

    # Suppliers
    sup_a = "sup-fresh"
    items.append({
        "record_type": RecordType.SUPPLIER.value,
        "status": "ACTIVE",
        "idempotency_key": f"seed:sup:{sup_a}",
        "body": {
            "supplier_id": sup_a,
            "name": "Fresh Valley Supplies (Demo)",
            "phone": "9800000099",
            "label": "demo/certification",
        },
    })
    items.append({
        "record_type": RecordType.SUPPLIER_ENTRY.value,
        "status": "RECORDED",
        "idempotency_key": "seed:supentry:opening",
        "body": {
            "supplier_id": sup_a,
            "delta_minor": 120000,  # 1200 NPR
            "currency": "NPR",
            "entry_type": "OPENING",
            "note": "Demo opening dues",
        },
    })

    # Sample historical paid order
    items.append({
        "record_type": RecordType.ORDER.value,
        "status": "PAID",
        "idempotency_key": "seed:order:hist1",
        "body": {
            "lines": [
                {
                    "menu_item_id": "menu-tea",
                    "name": "Milk Tea",
                    "qty": 2,
                    "unit_price_minor": 3000,
                    "discount_minor": 0,
                    "currency": "NPR",
                }
            ],
            "subtotal_minor": 6000,
            "discount_minor": 0,
            "total_minor": 6000,
            "paid_minor": 6000,
            "balance_minor": 0,
            "currency": "NPR",
            "channel": "dine_in",
            "token": "SEED01",
            "customer_id": "",
            "payment_ids": [],
            "label": "demo historical",
        },
    })
    items.append({
        "record_type": RecordType.PAYMENT.value,
        "status": "RECORDED",
        "idempotency_key": "seed:pay:hist1",
        "body": {
            "order_id": "seed-order-placeholder",
            "amount_minor": 6000,
            "currency": "NPR",
            "method": "CASH",
            "note": "Demo historical payment",
            "live_gateway": False,
        },
    })

    # Sample expense
    items.append({
        "record_type": RecordType.EXPENSE.value,
        "status": "RECORDED",
        "idempotency_key": "seed:exp:gas",
        "body": {
            "category": "utilities",
            "amount_minor": 15000,
            "currency": "NPR",
            "description": "Demo LPG cylinder (partial)",
            "payment_source": "CASH",
            "label": "demo/certification",
        },
    })

    # Low stock alert already open for oil
    items.append({
        "record_type": RecordType.ALERT.value,
        "status": "OPEN",
        "idempotency_key": "seed:alert:oil",
        "body": {
            "kind": "LOW_STOCK",
            "inventory_item_id": inv_oil,
            "name": "Cooking oil (L)",
            "qty_on_hand": 2,
            "min_qty": 5,
            "label": "demo/certification",
        },
    })

    return items
