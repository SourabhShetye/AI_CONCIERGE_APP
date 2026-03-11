"""
main.py - FastAPI application entry point.

Includes:
  - CORS middleware
  - All REST API routes (customer + staff)
  - WebSocket endpoints (customer updates + kitchen display)
  - Startup initialisation
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db, get_db
from app.auth import (
    hash_password, verify_password, create_access_token,
    get_current_user, require_staff, require_admin, require_customer,
)
from app.models import (
    CustomerRegisterRequest, CustomerLoginRequest, StaffLoginRequest,
    TokenResponse, PlaceOrderRequest, ModifyOrderRequest,
    CreateBookingRequest, FeedbackRequest, MenuItemCreate, MenuItemUpdate,
    RestaurantSettings, StaffUserCreate, OrderStatus,
)
from app.order_service import process_natural_language_order, process_modification
from app.booking_service import (
    parse_booking_datetime, validate_booking_time, can_cancel_booking,
    check_duplicate_booking, check_capacity,
)
from app.crm import compute_tags, build_welcome_message
from app.websocket import manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Restaurant AI Concierge API", version="2.0.0")

# ─── CORS ─────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Startup ──────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    init_db()
    logger.info("✅ Database client initialised")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}


# ═══════════════════════════════════════════════════════════════════════════════
# CUSTOMER AUTH
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/customer/register", response_model=TokenResponse)
async def customer_register(req: CustomerRegisterRequest):
    db = get_db()
    restaurant_id = req.restaurant_id or settings.default_restaurant_id

    # Check if customer already exists (same name + restaurant)
    existing = (
        db.table("user_sessions")
        .select("*")
        .eq("name", req.name)
        .eq("restaurant_id", restaurant_id)
        .execute()
    )
    if existing.data:
        raise HTTPException(status_code=409, detail="Name already registered. Please log in.")

    pin_hash = hash_password(req.pin)
    result = (
        db.table("user_sessions")
        .insert({
            "restaurant_id": restaurant_id,
            "name": req.name,
            "phone": req.phone,
            "pin_hash": pin_hash,
            "allergies": req.allergies or [],
            "visit_count": 0,
            "total_spend": 0.0,
            "tags": [],
            "table_number": req.table_number,
        })
        .execute()
    )
    user = result.data[0]

    token = create_access_token({
        "user_id": user["id"],
        "role": "customer",
        "restaurant_id": restaurant_id,
        "name": req.name,
    })
    return TokenResponse(
        access_token=token,
        role="customer",
        user_id=user["id"],
        name=req.name,
        visit_count=0,
        total_spend=0.0,
        tags=[],
    )


@app.post("/api/customer/login", response_model=TokenResponse)
async def customer_login(req: CustomerLoginRequest):
    db = get_db()
    restaurant_id = req.restaurant_id or settings.default_restaurant_id

    result = (
        db.table("user_sessions")
        .select("*")
        .eq("name", req.name)
        .eq("restaurant_id", restaurant_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=401, detail="Customer not found. Please register first.")

    user = result.data[0]
    if not verify_password(req.pin, user["pin_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect PIN.")

    # Update table number if provided
    if req.table_number:
        db.table("user_sessions").update({"table_number": req.table_number}).eq("id", user["id"]).execute()

    welcome = build_welcome_message(req.name, user.get("visit_count", 0), user.get("tags", []))
    token = create_access_token({
        "user_id": user["id"],
        "role": "customer",
        "restaurant_id": restaurant_id,
        "name": req.name,
        "welcome": welcome,
    })
    return TokenResponse(
        access_token=token,
        role="customer",
        user_id=user["id"],
        name=req.name,
        visit_count=user.get("visit_count", 0),
        total_spend=float(user.get("total_spend", 0)),
        tags=user.get("tags", []),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# STAFF AUTH
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/staff/login", response_model=TokenResponse)
async def staff_login(req: StaffLoginRequest):
    db = get_db()
    restaurant_id = req.restaurant_id or settings.default_restaurant_id

    result = (
        db.table("staff_users")
        .select("*")
        .eq("username", req.username)
        .eq("restaurant_id", restaurant_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=401, detail="Staff user not found.")

    staff = result.data[0]
    if not verify_password(req.password, staff["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect password.")

    token = create_access_token({
        "user_id": staff["id"],
        "role": staff["role"],
        "restaurant_id": restaurant_id,
        "name": req.username,
    })
    return TokenResponse(
        access_token=token,
        role=staff["role"],
        user_id=staff["id"],
        name=req.username,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MENU
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/menu")
async def get_menu(restaurant_id: Optional[str] = None):
    db = get_db()
    rid = restaurant_id or settings.default_restaurant_id
    result = db.table("menu_items").select("*").eq("restaurant_id", rid).execute()
    return result.data


@app.post("/api/staff/menu", dependencies=[Depends(require_staff)])
async def create_menu_item(item: MenuItemCreate, current_user: dict = Depends(require_staff)):
    db = get_db()
    result = db.table("menu_items").insert({
        **item.model_dump(),
        "restaurant_id": current_user["restaurant_id"],
    }).execute()
    return result.data[0]


@app.put("/api/staff/menu/{item_id}", dependencies=[Depends(require_staff)])
async def update_menu_item(item_id: str, item: MenuItemUpdate):
    db = get_db()
    updates = {k: v for k, v in item.model_dump().items() if v is not None}
    result = db.table("menu_items").update(updates).eq("id", item_id).execute()
    return result.data[0]


@app.delete("/api/staff/menu/{item_id}", dependencies=[Depends(require_staff)])
async def delete_menu_item(item_id: str):
    db = get_db()
    db.table("menu_items").delete().eq("id", item_id).execute()
    return {"detail": "Deleted"}


# ═══════════════════════════════════════════════════════════════════════════════
# ORDERS
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/orders")
async def place_order(req: PlaceOrderRequest, current_user: dict = Depends(require_customer)):
    db = get_db()
    restaurant_id = req.restaurant_id or current_user.get("restaurant_id") or settings.default_restaurant_id
    user_id = current_user["user_id"]

    # Fetch customer allergies
    user_data = db.table("user_sessions").select("allergies").eq("id", user_id).execute()
    allergies = (user_data.data[0].get("allergies") or []) if user_data.data else []

    # Fetch menu
    menu = db.table("menu_items").select("*").eq("restaurant_id", restaurant_id).execute()

    # Fetch restaurant AI context
    settings_row = db.table("restaurant_policies").select("ai_context").eq("restaurant_id", restaurant_id).execute()
    ai_context = (settings_row.data[0].get("ai_context") or "") if settings_row.data else ""

    # Parse order via AI
    try:
        parsed = await process_natural_language_order(
            req.natural_language_input,
            menu.data,
            allergies,
            ai_context,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if not parsed.items:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "No recognisable items found.",
                "unrecognized": parsed.unrecognized_items,
                "sold_out": parsed.sold_out_items,
            },
        )

    # Get customer name
    user_row = db.table("user_sessions").select("name").eq("id", user_id).execute()
    customer_name = user_row.data[0]["name"] if user_row.data else "Guest"

    # Insert order
    order_data = {
        "restaurant_id": restaurant_id,
        "user_id": user_id,
        "customer_name": customer_name,
        "table_number": req.table_number,
        "items": json.dumps([i.model_dump() for i in parsed.items]),
        "price": parsed.total,
        "status": "pending",
        "cancellation_status": "none",
        "modification_status": "none",
        "allergy_warnings": parsed.allergy_warnings,
    }
    result = db.table("orders").insert(order_data).execute()
    order = result.data[0]

    # Notify kitchen via WebSocket
    await manager.broadcast_to_kitchen(restaurant_id, "new_order", {
        "order_id": order["id"],
        "table_number": req.table_number,
        "customer_name": customer_name,
        "items": [i.model_dump() for i in parsed.items],
        "total": parsed.total,
        "allergy_warnings": parsed.allergy_warnings,
    })

    return {
        **order,
        "items": parsed.items,
        "allergy_warnings": parsed.allergy_warnings,
        "sold_out_items": parsed.sold_out_items,
        "unrecognized_items": parsed.unrecognized_items,
    }


@app.get("/api/orders")
async def get_customer_orders(current_user: dict = Depends(require_customer)):
    db = get_db()
    result = (
        db.table("orders")
        .select("*")
        .eq("user_id", current_user["user_id"])
        .order("created_at", desc=True)
        .execute()
    )
    orders = result.data
    for o in orders:
        if isinstance(o.get("items"), str):
            o["items"] = json.loads(o["items"])
    return orders


@app.put("/api/orders/{order_id}/modify")
async def modify_order(
    order_id: str,
    req: ModifyOrderRequest,
    current_user: dict = Depends(require_customer),
):
    db = get_db()
    order = db.table("orders").select("*").eq("id", order_id).execute()
    if not order.data:
        raise HTTPException(status_code=404, detail="Order not found.")
    o = order.data[0]
    if o["user_id"] != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Not your order.")
    if o["status"] not in ("pending", "preparing"):
        raise HTTPException(status_code=409, detail="Order cannot be modified at this stage.")

    current_items_raw = json.loads(o["items"]) if isinstance(o["items"], str) else o["items"]
    from app.models import OrderItem
    current_items = [OrderItem(**i) for i in current_items_raw]

    menu = db.table("menu_items").select("*").eq("restaurant_id", o["restaurant_id"]).execute()

    try:
        updated_items, new_total = await process_modification(req.modification_text, current_items, menu.data)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    db.table("orders").update({
        "items": json.dumps([i.model_dump() for i in updated_items]),
        "price": new_total,
        "modification_status": "requested",
    }).eq("id", order_id).execute()

    # Notify kitchen
    await manager.broadcast_to_kitchen(o["restaurant_id"], "modification_request", {
        "order_id": order_id,
        "modification_text": req.modification_text,
        "new_items": [i.model_dump() for i in updated_items],
        "new_total": new_total,
    })

    return {"detail": "Modification submitted for kitchen approval.", "new_total": new_total}


@app.delete("/api/orders/{order_id}")
async def cancel_order(order_id: str, current_user: dict = Depends(require_customer)):
    db = get_db()
    order = db.table("orders").select("*").eq("id", order_id).execute()
    if not order.data:
        raise HTTPException(status_code=404, detail="Order not found.")
    o = order.data[0]
    if o["user_id"] != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Not your order.")
    if o["status"] in ("completed", "cancelled"):
        raise HTTPException(status_code=409, detail="Order already completed or cancelled.")

    db.table("orders").update({"cancellation_status": "requested"}).eq("id", order_id).execute()

    await manager.broadcast_to_kitchen(o["restaurant_id"], "cancellation_request", {
        "order_id": order_id,
        "customer_name": o.get("customer_name"),
        "table_number": o.get("table_number"),
    })
    return {"detail": "Cancellation requested. Awaiting kitchen approval."}


# ═══════════════════════════════════════════════════════════════════════════════
# STAFF ORDER ACTIONS
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/staff/orders", dependencies=[Depends(require_staff)])
async def kitchen_orders(current_user: dict = Depends(require_staff)):
    db = get_db()
    result = (
        db.table("orders")
        .select("*")
        .eq("restaurant_id", current_user["restaurant_id"])
        .not_.in_("status", ["completed", "cancelled"])
        .order("created_at")
        .execute()
    )
    orders = result.data
    for o in orders:
        if isinstance(o.get("items"), str):
            o["items"] = json.loads(o["items"])
    return orders


@app.put("/api/staff/orders/{order_id}/ready", dependencies=[Depends(require_staff)])
async def mark_order_ready(order_id: str, current_user: dict = Depends(require_staff)):
    db = get_db()
    order = db.table("orders").select("*").eq("id", order_id).execute()
    if not order.data:
        raise HTTPException(status_code=404, detail="Order not found.")
    o = order.data[0]
    db.table("orders").update({"status": "ready"}).eq("id", order_id).execute()

    # Notify customer
    await manager.send_to_customer(o["user_id"], "order_ready", {"order_id": order_id})
    return {"detail": "Order marked ready."}


@app.put("/api/staff/orders/{order_id}/approve_modification", dependencies=[Depends(require_staff)])
async def approve_modification(order_id: str):
    db = get_db()
    order = db.table("orders").select("*").eq("id", order_id).execute()
    if not order.data:
        raise HTTPException(status_code=404, detail="Order not found.")
    o = order.data[0]
    db.table("orders").update({"modification_status": "approved"}).eq("id", order_id).execute()
    await manager.send_to_customer(o["user_id"], "modification_approved", {"order_id": order_id})
    return {"detail": "Modification approved."}


@app.put("/api/staff/orders/{order_id}/reject_modification", dependencies=[Depends(require_staff)])
async def reject_modification(order_id: str):
    db = get_db()
    order = db.table("orders").select("*").eq("id", order_id).execute()
    if not order.data:
        raise HTTPException(404, "Order not found.")
    o = order.data[0]
    db.table("orders").update({"modification_status": "rejected"}).eq("id", order_id).execute()
    await manager.send_to_customer(o["user_id"], "modification_rejected", {"order_id": order_id})
    return {"detail": "Modification rejected."}


@app.put("/api/staff/orders/{order_id}/approve_cancellation", dependencies=[Depends(require_staff)])
async def approve_cancellation(order_id: str):
    db = get_db()
    order = db.table("orders").select("*").eq("id", order_id).execute()
    if not order.data:
        raise HTTPException(404, "Order not found.")
    o = order.data[0]
    db.table("orders").update({
        "status": "cancelled",
        "cancellation_status": "approved",
    }).eq("id", order_id).execute()
    await manager.send_to_customer(o["user_id"], "order_cancelled", {"order_id": order_id})
    return {"detail": "Cancellation approved."}


@app.put("/api/staff/orders/{order_id}/reject_cancellation", dependencies=[Depends(require_staff)])
async def reject_cancellation(order_id: str):
    db = get_db()
    order = db.table("orders").select("*").eq("id", order_id).execute()
    if not order.data:
        raise HTTPException(404, "Order not found.")
    o = order.data[0]
    db.table("orders").update({"cancellation_status": "rejected"}).eq("id", order_id).execute()
    await manager.send_to_customer(o["user_id"], "cancellation_rejected", {"order_id": order_id})
    return {"detail": "Cancellation rejected."}


# ═══════════════════════════════════════════════════════════════════════════════
# TABLES & BILLING
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/staff/tables", dependencies=[Depends(require_staff)])
async def live_tables(current_user: dict = Depends(require_staff)):
    """Group active orders by table number."""
    db = get_db()
    result = (
        db.table("orders")
        .select("*")
        .eq("restaurant_id", current_user["restaurant_id"])
        .not_.in_("status", ["completed", "cancelled"])
        .execute()
    )
    orders = result.data
    for o in orders:
        if isinstance(o.get("items"), str):
            o["items"] = json.loads(o["items"])

    tables: dict = {}
    for o in orders:
        tbl = o.get("table_number", "Unknown")
        if tbl not in tables:
            tables[tbl] = {"table_number": tbl, "orders": [], "total": 0.0}
        tables[tbl]["orders"].append(o)
        tables[tbl]["total"] = round(tables[tbl]["total"] + float(o.get("price", 0)), 2)

    return list(tables.values())


@app.post("/api/staff/tables/{table_number}/close", dependencies=[Depends(require_staff)])
async def close_table(table_number: str, current_user: dict = Depends(require_staff)):
    """
    Close a table (payment received):
    1. Mark all orders as completed + paid
    2. Update CRM (visit_count, total_spend, tags)
    3. Trigger feedback request to customers
    """
    db = get_db()
    restaurant_id = current_user["restaurant_id"]

    orders = (
        db.table("orders")
        .select("*")
        .eq("restaurant_id", restaurant_id)
        .eq("table_number", table_number)
        .not_.in_("status", ["completed", "cancelled"])
        .execute()
    )
    if not orders.data:
        raise HTTPException(status_code=404, detail="No active orders for this table.")

    total = sum(float(o.get("price", 0)) for o in orders.data)
    user_ids = list({o["user_id"] for o in orders.data})

    # Mark orders paid/completed
    for o in orders.data:
        db.table("orders").update({"status": "completed"}).eq("id", o["id"]).execute()

    # Update CRM for each customer at table
    for uid in user_ids:
        user = db.table("user_sessions").select("*").eq("id", uid).execute()
        if not user.data:
            continue
        u = user.data[0]
        new_visit = u.get("visit_count", 0) + 1
        new_spend = float(u.get("total_spend", 0)) + total
        tags = compute_tags(new_visit, new_spend, u.get("last_visit"))
        db.table("user_sessions").update({
            "visit_count": new_visit,
            "total_spend": new_spend,
            "tags": tags,
            "last_visit": datetime.now(timezone.utc).isoformat(),
        }).eq("id", uid).execute()

        # Notify customer: feedback request
        await manager.send_to_customer(uid, "feedback_requested", {
            "table_number": table_number,
            "total": total,
        })

    return {"detail": f"Table {table_number} closed. Total: AED {total:.2f}"}


@app.get("/api/bill/{table_number}")
async def get_bill(table_number: str, restaurant_id: Optional[str] = None):
    db = get_db()
    rid = restaurant_id or settings.default_restaurant_id
    result = (
        db.table("orders")
        .select("*")
        .eq("restaurant_id", rid)
        .eq("table_number", table_number)
        .not_.in_("status", ["cancelled"])
        .execute()
    )
    orders = result.data
    for o in orders:
        if isinstance(o.get("items"), str):
            o["items"] = json.loads(o["items"])

    total = sum(float(o.get("price", 0)) for o in orders)
    return {"table_number": table_number, "orders": orders, "total": round(total, 2)}


# ═══════════════════════════════════════════════════════════════════════════════
# BOOKINGS
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/bookings")
async def create_booking(req: CreateBookingRequest, current_user: dict = Depends(require_customer)):
    db = get_db()
    restaurant_id = req.restaurant_id or current_user.get("restaurant_id") or settings.default_restaurant_id
    user_id = current_user["user_id"]

    booking_time = parse_booking_datetime(req.booking_time)
    if not booking_time:
        raise HTTPException(status_code=422, detail="Invalid booking time format. Use ISO 8601.")

    valid, err = validate_booking_time(booking_time)
    if not valid:
        raise HTTPException(status_code=422, detail=err)

    # Check for duplicate
    existing = db.table("bookings").select("*").eq("restaurant_id", restaurant_id).execute()
    if check_duplicate_booking(existing.data, user_id, booking_time):
        raise HTTPException(status_code=409, detail="You already have a booking around that time.")

    # Check capacity
    settings_row = db.table("restaurant_policies").select("table_count, max_party_size").eq("restaurant_id", restaurant_id).execute()
    table_count = (settings_row.data[0].get("table_count") or 20) if settings_row.data else 20
    max_party = (settings_row.data[0].get("max_party_size") or 10) if settings_row.data else 10

    ok, cap_err = check_capacity(existing.data, booking_time, req.party_size, table_count, max_party)
    if not ok:
        raise HTTPException(status_code=409, detail=cap_err)

    user_row = db.table("user_sessions").select("name").eq("id", user_id).execute()
    customer_name = user_row.data[0]["name"] if user_row.data else "Guest"

    result = db.table("bookings").insert({
        "restaurant_id": restaurant_id,
        "user_id": user_id,
        "customer_name": customer_name,
        "party_size": req.party_size,
        "booking_time": booking_time.isoformat(),
        "status": "confirmed",
        "special_requests": req.special_requests,
    }).execute()

    return result.data[0]


@app.get("/api/bookings")
async def get_customer_bookings(current_user: dict = Depends(require_customer)):
    db = get_db()
    result = (
        db.table("bookings")
        .select("*")
        .eq("user_id", current_user["user_id"])
        .order("booking_time", desc=True)
        .execute()
    )
    return result.data


@app.delete("/api/bookings/{booking_id}")
async def cancel_booking(booking_id: str, current_user: dict = Depends(require_customer)):
    db = get_db()
    booking = db.table("bookings").select("*").eq("id", booking_id).execute()
    if not booking.data:
        raise HTTPException(status_code=404, detail="Booking not found.")
    b = booking.data[0]
    if b["user_id"] != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Not your booking.")

    from datetime import datetime
    bt = datetime.fromisoformat(b["booking_time"])
    ok, err = can_cancel_booking(bt)
    if not ok:
        raise HTTPException(status_code=409, detail=err)

    db.table("bookings").update({"status": "cancelled"}).eq("id", booking_id).execute()
    return {"detail": "Booking cancelled."}


@app.get("/api/staff/bookings", dependencies=[Depends(require_staff)])
async def staff_get_bookings(current_user: dict = Depends(require_staff)):
    db = get_db()
    result = (
        db.table("bookings")
        .select("*")
        .eq("restaurant_id", current_user["restaurant_id"])
        .order("booking_time")
        .execute()
    )
    return result.data


@app.put("/api/staff/bookings/{booking_id}/confirm", dependencies=[Depends(require_staff)])
async def confirm_booking(booking_id: str):
    db = get_db()
    db.table("bookings").update({"status": "confirmed"}).eq("id", booking_id).execute()
    return {"detail": "Booking confirmed."}


@app.delete("/api/staff/bookings/{booking_id}", dependencies=[Depends(require_staff)])
async def staff_cancel_booking(booking_id: str):
    db = get_db()
    db.table("bookings").update({"status": "cancelled"}).eq("id", booking_id).execute()
    return {"detail": "Booking cancelled."}


# ═══════════════════════════════════════════════════════════════════════════════
# FEEDBACK
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/feedback")
async def submit_feedback(req: FeedbackRequest, current_user: dict = Depends(require_customer)):
    db = get_db()
    restaurant_id = req.restaurant_id or current_user.get("restaurant_id") or settings.default_restaurant_id
    result = db.table("feedback").insert({
        "restaurant_id": restaurant_id,
        "user_id": current_user["user_id"],
        "ratings": json.dumps(req.order_ratings),
        "overall_rating": req.overall_rating,
        "comments": req.comments,
    }).execute()
    return result.data[0]


# ═══════════════════════════════════════════════════════════════════════════════
# CRM
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/staff/crm", dependencies=[Depends(require_staff)])
async def get_crm(current_user: dict = Depends(require_staff)):
    db = get_db()
    result = (
        db.table("user_sessions")
        .select("*")
        .eq("restaurant_id", current_user["restaurant_id"])
        .order("total_spend", desc=True)
        .execute()
    )
    return result.data


# ═══════════════════════════════════════════════════════════════════════════════
# SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/staff/settings", dependencies=[Depends(require_staff)])
async def get_settings(current_user: dict = Depends(require_staff)):
    db = get_db()
    result = db.table("restaurant_policies").select("*").eq("restaurant_id", current_user["restaurant_id"]).execute()
    return result.data[0] if result.data else {}


@app.put("/api/staff/settings", dependencies=[Depends(require_staff)])
async def update_settings(req: RestaurantSettings, current_user: dict = Depends(require_staff)):
    db = get_db()
    rid = current_user["restaurant_id"]
    existing = db.table("restaurant_policies").select("id").eq("restaurant_id", rid).execute()
    updates = req.model_dump(exclude_none=True)
    updates["restaurant_id"] = rid
    if existing.data:
        db.table("restaurant_policies").update(updates).eq("restaurant_id", rid).execute()
    else:
        db.table("restaurant_policies").insert(updates).execute()
    return {"detail": "Settings updated."}


# ═══════════════════════════════════════════════════════════════════════════════
# STAFF USER MANAGEMENT (admin only)
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/staff/users", dependencies=[Depends(require_admin)])
async def create_staff_user(req: StaffUserCreate, current_user: dict = Depends(require_admin)):
    db = get_db()
    result = db.table("staff_users").insert({
        "username": req.username,
        "password_hash": hash_password(req.password),
        "role": req.role,
        "restaurant_id": req.restaurant_id or current_user["restaurant_id"],
    }).execute()
    return {"detail": "Staff user created.", "id": result.data[0]["id"]}


# ═══════════════════════════════════════════════════════════════════════════════
# WEBSOCKET ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@app.websocket("/ws/customer/{session_id}")
async def customer_ws(websocket: WebSocket, session_id: str):
    await manager.connect_customer(session_id, websocket)
    try:
        while True:
            await websocket.receive_text()  # Keep alive
    except WebSocketDisconnect:
        manager.disconnect_customer(session_id)


@app.websocket("/ws/kitchen/{restaurant_id}")
async def kitchen_ws(websocket: WebSocket, restaurant_id: str):
    await manager.connect_kitchen(restaurant_id, websocket)
    try:
        while True:
            await websocket.receive_text()  # Keep alive
    except WebSocketDisconnect:
        manager.disconnect_kitchen(restaurant_id, websocket)
