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
import qrcode
import io
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi import UploadFile, File
from app.chat_service import process_chat
from datetime import datetime, timezone
from typing import Optional, List
from app.staff_chat_service import process_staff_chat

from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db, get_db
from app.auth import (
    hash_password, verify_password, create_access_token,
    get_current_user, require_staff, require_admin, require_customer,
)
from pydantic import BaseModel
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
from datetime import date as _date

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Restaurant AI Concierge API", version="2.0.0")
async def get_next_order_number(db, restaurant_id: str) -> int:
    """
    Returns the next daily order number for a restaurant.
    Resets to 1 each day. e.g. Order #1, #2, #3 ... resets next day.
    """
    today = _date.today().isoformat()
    try:
        existing = db.table("order_number_sequences").select("*").eq(
            "restaurant_id", restaurant_id
        ).eq("date", today).execute()

        if existing.data:
            new_number = existing.data[0]["last_number"] + 1
            db.table("order_number_sequences").update(
                {"last_number": new_number}
            ).eq("restaurant_id", restaurant_id).eq("date", today).execute()
        else:
            new_number = 1
            db.table("order_number_sequences").insert({
                "restaurant_id": restaurant_id,
                "date": today,
                "last_number": 1,
            }).execute()

        return new_number
    except Exception as e:
        logger.error(f"Order number generation failed: {e}")
        return 0  # fallback — 0 means unassigned

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
    logger.info(f"Customer login: name={req.name} restaurant_id={restaurant_id}")

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
        "restaurant_id": user["restaurant_id"],  # from DB record
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
    # Always use restaurant_id from the DB record — never trust the request
    token = create_access_token({
        "user_id": user["id"],
        "role": "customer",
        "restaurant_id": user["restaurant_id"],  # from DB, guaranteed correct
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

    # Search by username only — no restaurant_id filter
    # This allows each restaurant's admin to log in without knowing their UUID
    result = (
        db.table("staff_users")
        .select("*")
        .eq("username", req.username)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=401, detail="Staff user not found.")

    staff = result.data[0]
    if not verify_password(req.password, staff["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect password.")

    # Restaurant ID comes from the staff record itself — not the request
    restaurant_id = staff["restaurant_id"]

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
# RESTAURANT INFO
# ═══════════════════════════════════════════════════════════════════════════════
@app.get("/api/restaurant/{restaurant_id}")
async def get_restaurant(restaurant_id: str):
    """Public endpoint — returns basic restaurant info for the header."""
    db = get_db()
    result = db.table("restaurants").select("id, name").eq("id", restaurant_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    return result.data[0]

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
    # JWT restaurant_id is the source of truth — prevents cross-tenant data access
    restaurant_id = current_user.get("restaurant_id") or req.restaurant_id or settings.default_restaurant_id
    logger.info(f"Chat request: user={current_user.get('user_id')} restaurant={restaurant_id} mode={req.mode}")
    user_id = current_user["user_id"]

    # Fetch customer allergies
    user_data = db.table("user_sessions").select("allergies").eq("id", user_id).execute()
    allergies = (user_data.data[0].get("allergies") or []) if user_data.data else []

    # Fetch menu
    menu = db.table("menu_items").select("*").eq("restaurant_id", restaurant_id).eq("sold_out", False).execute()
    if not menu.data:
        # Fallback: fetch all items including sold out so AI still has context
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
    daily_number = await get_next_order_number(db, restaurant_id)
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
        "daily_order_number": daily_number,
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
async def get_customer_orders(current_user: dict = Depends(get_current_user)):
    db = get_db()
    # Resolve real user_id from user_sessions if needed
    user_id = current_user["user_id"]
    restaurant_id = current_user.get("restaurant_id") or settings.default_restaurant_id

    # Verify this user_id exists — if not, find by name
    check = db.table("user_sessions").select("id").eq("id", user_id).execute()
    if not check.data:
        by_name = db.table("user_sessions").select("id").eq(
            "restaurant_id", restaurant_id
        ).eq("name", current_user.get("name", "")).execute()
        if by_name.data:
            user_id = by_name.data[0]["id"]
        else:
            raise HTTPException(status_code=404, detail="Session not found. Please log in again.")
    logger.info(f"Fetching orders for user={current_user['user_id']} restaurant={current_user.get('restaurant_id')}")
    result = (
        db.table("orders")
        .select("*")
        .eq("user_id", current_user["user_id"])
        .order("created_at", desc=True)
        .execute()
    )
    orders = result.data
    logger.info(f"Found {len(orders)} orders for user={current_user['user_id']}")
    for o in orders:
        if isinstance(o.get("items"), str):
            try:
                o["items"] = json.loads(o["items"])
            except Exception:
                o["items"] = []
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
    items_raw = o.get("items", "[]")
    if isinstance(items_raw, str):
        items_list = json.loads(items_raw)
    else:
        items_list = items_raw
    items_summary = ", ".join([
        f"{i.get('quantity',1)}x {i.get('name','')}" for i in items_list
    ])
    order_num = o.get("daily_order_number", "?")
    db.table("orders").update({"modification_status": "approved"}).eq("id", order_id).execute()
    await manager.send_to_customer(o["user_id"], "modification_approved", {
        "order_id": order_id,
        "order_number": order_num,
        "items_summary": items_summary,
        "chat_message": f"✅ Your modification for Order #{order_num} has been approved by the kitchen.",
    })
    return {"detail": "Modification approved."}


@app.put("/api/staff/orders/{order_id}/reject_modification", dependencies=[Depends(require_staff)])
async def reject_modification(order_id: str):
    db = get_db()
    order = db.table("orders").select("*").eq("id", order_id).execute()
    if not order.data:
        raise HTTPException(404, "Order not found.")
    o = order.data[0]
    items_raw = o.get("items", "[]")
    if isinstance(items_raw, str):
        items_list = json.loads(items_raw)
    else:
        items_list = items_raw
    items_summary = ", ".join([
        f"{i.get('quantity',1)}x {i.get('name','')}" for i in items_list
    ])
    order_num = o.get("daily_order_number", "?")
    db.table("orders").update({"modification_status": "rejected"}).eq("id", order_id).execute()
    await manager.send_to_customer(o["user_id"], "modification_rejected", {
        "order_id": order_id,
        "order_number": order_num,
        "items_summary": items_summary,
        "chat_message": f"❌ Your modification request for Order #{order_num} ({items_summary}) was rejected. Original order stands.",
    })
    return {"detail": "Modification rejected."}


@app.put("/api/staff/orders/{order_id}/approve_cancellation", dependencies=[Depends(require_staff)])
async def approve_cancellation(order_id: str):
    db = get_db()
    order = db.table("orders").select("*").eq("id", order_id).execute()
    if not order.data:
        raise HTTPException(404, "Order not found.")
    o = order.data[0]

    items_raw = o.get("items", "[]")
    if isinstance(items_raw, str):
        items_list = json.loads(items_raw)
    else:
        items_list = items_raw

    cancel_desc = o.get("modification_text") or ""
    order_num = o.get("daily_order_number", "?")
    is_partial = cancel_desc.lower().startswith("remove:")

    if is_partial:
        items_to_remove_raw = cancel_desc.replace("Remove:", "").replace("remove:", "").strip()
        items_to_remove = [i.strip().lower() for i in items_to_remove_raw.split(",")]

        kept_items = []
        cancelled_items = []
        for item in items_list:
            name_lower = item.get("name", "").lower()
            if any(rm in name_lower or name_lower in rm for rm in items_to_remove):
                cancelled_items.append(item)
            else:
                kept_items.append(item)

        new_price = round(sum(
            float(i.get("unit_price", 0)) * int(i.get("quantity", 1))
            for i in kept_items
        ), 2)

        if kept_items:
            try:
                db.table("orders").update({
                    "items": json.dumps(kept_items),
                    "price": new_price,
                    "cancellation_status": "approved",
                    "modification_text": cancel_desc,
                }).eq("id", order_id).execute()
            except Exception as e:
                logger.error(f"Partial cancel update failed: {e}")
                raise HTTPException(status_code=500, detail=f"Database update failed: {e}")

            removed_summary = ", ".join([f"{i.get('quantity',1)}x {i.get('name','')}" for i in cancelled_items])
            kept_summary = ", ".join([f"{i.get('quantity',1)}x {i.get('name','')}" for i in kept_items])
            chat_message = (
                f"✅ Partial cancellation approved for Order #{order_num}.\n"
                f"Removed: {removed_summary}\n"
                f"Remaining: {kept_summary} (AED {new_price:.2f})"
            )
        else:
            db.table("orders").update({
                "status": "cancelled",
                "cancellation_status": "approved",
            }).eq("id", order_id).execute()
            chat_message = f"✅ Order #{order_num} fully cancelled — all items removed."

    else:
        # Full cancellation
        items_summary = ", ".join([f"{i.get('quantity',1)}x {i.get('name','')}" for i in items_list])
        db.table("orders").update({
            "status": "cancelled",
            "cancellation_status": "approved",
        }).eq("id", order_id).execute()
        chat_message = (
            f"✅ Your cancellation for Order #{order_num} ({items_summary}) "
            f"has been approved by the kitchen."
        )

    await manager.send_to_customer(o["user_id"], "order_cancelled", {
        "order_id": order_id,
        "order_number": order_num,
        "chat_message": chat_message,
    })
    logger.info(f"Cancellation approved: order #{order_num} partial={is_partial}")
    return {"detail": "Cancellation approved.", "partial": is_partial}



@app.put("/api/staff/orders/{order_id}/reject_cancellation", dependencies=[Depends(require_staff)])
async def reject_cancellation(order_id: str):
    db = get_db()
    order = db.table("orders").select("*").eq("id", order_id).execute()
    if not order.data:
        raise HTTPException(404, "Order not found.")
    o = order.data[0]
    items_raw = o.get("items", "[]")
    if isinstance(items_raw, str):
        items_list = json.loads(items_raw)
    else:
        items_list = items_raw
    items_summary = ", ".join([
        f"{i.get('quantity',1)}x {i.get('name','')}" for i in items_list
    ])
    order_num = o.get("daily_order_number", "?")
    db.table("orders").update({"cancellation_status": "rejected"}).eq("id", order_id).execute()
    await manager.send_to_customer(o["user_id"], "cancellation_rejected", {
        "order_id": order_id,
        "order_number": order_num,
        "items_summary": items_summary,
        "chat_message": f"❌ Your cancellation request for Order #{order_num} ({items_summary}) was rejected. Your order is being prepared.",
    })
    return {"detail": "Cancellation rejected."}

# ─────────────────────────────────────────────────────────────────────────────
# FEATURE 2: STAFF AI CHAT
# ─────────────────────────────────────────────────────────────────────────────

class StaffChatRequest(BaseModel):
    message: str
    conversation_history: list = []


@app.post("/api/staff/chat")
async def staff_chat(
    req: StaffChatRequest,
    current_user: dict = Depends(require_staff),
):
    """
    Staff-only AI assistant with full operational context.
    Can answer questions about orders, bookings, customers, revenue.
    Can send messages to specific customer tables.
    """
    db = get_db()
    restaurant_id = current_user["restaurant_id"]
    staff_name = current_user.get("name", "Staff")
    staff_role = current_user.get("role", "staff")

    # Fetch all operational data
    active_orders = (
        db.table("orders")
        .select("*")
        .eq("restaurant_id", restaurant_id)
        .not_.in_("status", ["completed", "cancelled"])
        .order("created_at")
        .execute()
    ).data or []

    for o in active_orders:
        if isinstance(o.get("items"), str):
            o["items"] = json.loads(o["items"])

    # Upcoming bookings (next 7 days)
    from datetime import timedelta as _td
    now = datetime.now(timezone.utc)
    week_ahead = (now + _td(days=7)).isoformat()
    bookings = (
        db.table("bookings")
        .select("*")
        .eq("restaurant_id", restaurant_id)
        .not_.eq("status", "cancelled")
        .gte("booking_time", now.isoformat())
        .lte("booking_time", week_ahead)
        .order("booking_time")
        .execute()
    ).data or []

    menu = (
        db.table("menu_items")
        .select("*")
        .eq("restaurant_id", restaurant_id)
        .execute()
    ).data or []

    customers = (
        db.table("user_sessions")
        .select("*")
        .eq("restaurant_id", restaurant_id)
        .execute()
    ).data or []

    settings_row = (
        db.table("restaurant_policies")
        .select("ai_context")
        .eq("restaurant_id", restaurant_id)
        .execute()
    )
    ai_context = (settings_row.data[0].get("ai_context") or "") if settings_row.data else ""

    from app.staff_chat_service import process_staff_chat
    result = await process_staff_chat(
        message=req.message,
        restaurant_id=restaurant_id,
        staff_name=staff_name,
        staff_role=staff_role,
        active_orders=active_orders,
        bookings=bookings,
        menu=menu,
        customers=customers,
        conversation_history=req.conversation_history,
        ai_context=ai_context,
    )

    # ── Handle send_customer_message action ───────────────────────────────────
    if result.get("action_type") == "send_customer_message":
        action_data = result.get("action_data", {})
        table_number = action_data.get("table_number")
        customer_message = action_data.get("message", "")

        if table_number and customer_message:
            # Find customers at this table and send them a WebSocket message
            seated = [
                c for c in customers
                if str(c.get("table_number")) == str(table_number)
            ]
            for customer in seated:
                await manager.send_to_customer(customer["id"], "staff_message", {
                    "message": customer_message,
                    "from": "Restaurant",
                    "chat_message": f"💬 Message from restaurant: {customer_message}",
                })
            logger.info(
                f"Staff message sent to table {table_number}: {customer_message}"
            )

    return result

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

    blocking_orders = [
        o for o in orders.data
        if o.get("status") in ("pending", "preparing")
    ]
    if blocking_orders:
        blocking_nums = [
            f"Order #{o.get('daily_order_number', '?')} ({o.get('status')})"
            for o in blocking_orders
        ]
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot close table — {len(blocking_orders)} order(s) still in kitchen: "
                f"{', '.join(blocking_nums)}. Mark all orders as Ready before closing."
            )
        )

    total = sum(float(o.get("price", 0)) for o in orders.data)
    user_ids = list({o["user_id"] for o in orders.data if o.get("user_id")})

    # Mark all orders completed — do this first, separately from CRM
    for o in orders.data:
        try:
            db.table("orders").update({"status": "completed"}).eq("id", o["id"]).execute()
        except Exception as e:
            logger.error(f"Failed to mark order {o['id']} completed: {e}")

    # CRM update — wrapped in its own try/except so a column error never kills this
    crm_errors = []
    for uid in user_ids:
        try:
            user = db.table("user_sessions").select("*").eq("id", uid).execute()
            if not user.data:
                continue
            u = user.data[0]
            new_visit = int(u.get("visit_count") or 0) + 1
            new_spend = float(u.get("total_spend") or 0) + total
            tags = compute_tags(new_visit, new_spend, u.get("last_visit"))

            db.table("user_sessions").update({
                "visit_count": new_visit,
                "total_spend": round(new_spend, 2),
                "tags": tags,
                "last_visit": datetime.now(timezone.utc).isoformat(),
                # Do NOT clear table_number here — needed for feedback after close
            }).eq("id", uid).execute()
            logger.info(f"CRM updated: uid={uid} visits={new_visit} spend={new_spend} tags={tags}")

        except Exception as e:
            crm_errors.append(str(e))
            logger.error(f"CRM update failed for {uid}: {e}")

    # Notify customers — wrapped separately
    for uid in user_ids:
        try:
            await manager.send_to_customer(uid, "feedback_requested", {
                "table_number": table_number,
                "total": total,
                "chat_message": (
                    f"✅ Your bill of AED {total:.2f} has been processed. "
                    f"Thank you for dining with us! Please leave us feedback ⭐"
                ),
            })
        except Exception as e:
            logger.error(f"WebSocket notify failed for {uid}: {e}")

    response = {
        "detail": f"Table {table_number} closed. Total: AED {total:.2f}",
        "total": total,
        "orders_closed": len(orders.data),
    }
    if crm_errors:
        response["crm_warnings"] = crm_errors  # visible in response but doesn't fail the close
    return response
    
@app.get("/api/my-bill")
async def get_my_bill(current_user: dict = Depends(get_current_user)):
    """
    Returns current active bill AND full past bill history
    for this customer, grouped by visit date.
    """
    db = get_db()
    user_id = current_user["user_id"]
    restaurant_id = current_user.get("restaurant_id") or settings.default_restaurant_id

    user_data = db.table("user_sessions").select(
        "id, table_number, name"
    ).eq("id", user_id).execute()

    if not user_data.data:
        raise HTTPException(status_code=404, detail="Session not found.")

    table_number = user_data.data[0].get("table_number")

    # ── Current active orders ─────────────────────────────────────────────────
    if table_number:
        active_result = (
            db.table("orders")
            .select("*")
            .eq("restaurant_id", restaurant_id)
            .eq("table_number", table_number)
            .not_.in_("status", ["completed", "cancelled"])
            .order("created_at")
            .execute()
        )
    else:
        active_result = (
            db.table("orders")
            .select("*")
            .eq("user_id", user_id)
            .eq("restaurant_id", restaurant_id)
            .not_.in_("status", ["completed", "cancelled"])
            .order("created_at")
            .execute()
        )

    active_orders = active_result.data or []
    for o in active_orders:
        if isinstance(o.get("items"), str):
            o["items"] = json.loads(o["items"])

    active_total = round(sum(float(o.get("price", 0)) for o in active_orders), 2)

    # ── Past completed orders (all time, this restaurant) ────────────────────
    past_result = (
        db.table("orders")
        .select("*")
        .eq("user_id", user_id)
        .eq("restaurant_id", restaurant_id)
        .eq("status", "completed")
        .order("created_at", desc=True)
        .execute()
    )

    past_orders = past_result.data or []
    for o in past_orders:
        if isinstance(o.get("items"), str):
            o["items"] = json.loads(o["items"])

    # ── Group past orders by date ─────────────────────────────────────────────
    from collections import defaultdict
    past_by_date: dict = defaultdict(list)
    for o in past_orders:
        try:
            created = datetime.fromisoformat(o["created_at"])
            date_key = created.strftime("%d %B %Y")  # e.g. "15 January 2025"
        except Exception:
            date_key = "Unknown date"
        past_by_date[date_key].append(o)

    # Build past sessions (group by date + table)
    past_sessions = []
    for date_str, date_orders in past_by_date.items():
        # Group by table within the date
        table_groups: dict = defaultdict(list)
        for o in date_orders:
            tbl = o.get("table_number") or "Unknown"
            table_groups[tbl].append(o)

        for tbl, tbl_orders in table_groups.items():
            session_total = round(sum(float(o.get("price", 0)) for o in tbl_orders), 2)
            past_sessions.append({
                "date": date_str,
                "table_number": tbl,
                "orders": tbl_orders,
                "total": session_total,
            })

    return {
        "table_number": table_number,
        "active_orders": active_orders,
        "active_total": active_total,
        "is_paid": len(active_orders) == 0,
        "past_sessions": past_sessions,
        "lifetime_total": round(sum(s["total"] for s in past_sessions), 2),
    }

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


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE 3: TABLE INVENTORY MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/staff/tables-inventory", dependencies=[Depends(require_staff)])
async def get_tables_inventory(current_user: dict = Depends(require_staff)):
    """Get all tables with their capacities for this restaurant."""
    db = get_db()
    result = (
        db.table("tables_inventory")
        .select("*")
        .eq("restaurant_id", current_user["restaurant_id"])
        .order("capacity")
        .execute()
    )
    return result.data


@app.post("/api/staff/tables-inventory", dependencies=[Depends(require_staff)])
async def create_table(
    table_data: dict,
    current_user: dict = Depends(require_staff),
):
    """Add a new table to the inventory."""
    db = get_db()
    result = db.table("tables_inventory").insert({
        "restaurant_id": current_user["restaurant_id"],
        "table_number": str(table_data["table_number"]),
        "capacity": int(table_data["capacity"]),
        "is_active": table_data.get("is_active", True),
    }).execute()
    return result.data[0]


@app.put("/api/staff/tables-inventory/{table_id}", dependencies=[Depends(require_staff)])
async def update_table(table_id: str, table_data: dict):
    """Update table capacity or active status."""
    db = get_db()
    updates = {}
    if "capacity" in table_data:
        updates["capacity"] = int(table_data["capacity"])
    if "is_active" in table_data:
        updates["is_active"] = bool(table_data["is_active"])
    if "table_number" in table_data:
        updates["table_number"] = str(table_data["table_number"])

    result = db.table("tables_inventory").update(updates).eq("id", table_id).execute()
    return result.data[0]


@app.delete("/api/staff/tables-inventory/{table_id}", dependencies=[Depends(require_staff)])
async def delete_table(table_id: str):
    """Remove a table from inventory."""
    db = get_db()
    db.table("tables_inventory").delete().eq("id", table_id).execute()
    return {"detail": "Table removed."}

# ═══════════════════════════════════════════════════════════════════════════════
# BOOKINGS
# ═══════════════════════════════════════════════════════════════════════════════

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

@app.post("/api/bookings")
async def create_booking(
    req: CreateBookingRequest,
    current_user: dict = Depends(require_customer),
):
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

    assigned_table_id = None
    assigned_table_number = None

    # ── Try smart table allocation (only if tables_inventory exists) ──────────
    try:
        tables_result = (
            db.table("tables_inventory")
            .select("*")
            .eq("restaurant_id", restaurant_id)
            .eq("is_active", True)
            .execute()
        )

        if tables_result.data:
            from app.booking_service import (
                get_tables_booked_in_slot,
                find_best_table,
                get_available_slots,
            )

            booked_ids = get_tables_booked_in_slot(existing.data, booking_time)
            best_table = find_best_table(tables_result.data, req.party_size, booked_ids)

            if not best_table:
                available_slots = get_available_slots(
                    tables_result.data,
                    existing.data,
                    req.party_size,
                    booking_time,
                )
                if available_slots:
                    slots_str = ", ".join(available_slots[:5])
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"No table available for {req.party_size} guests at that time. "
                            f"Available slots on the same day: {slots_str}"
                        )
                    )
                else:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"No tables available for {req.party_size} guests on that date. "
                            f"Please try a different date."
                        )
                    )

            assigned_table_id = best_table["id"]
            assigned_table_number = best_table["table_number"]
            logger.info(
                f"Assigned table #{assigned_table_number} "
                f"(capacity {best_table['capacity']}) for party of {req.party_size}"
            )
        else:
            # No table inventory configured — use legacy capacity check
            raise ValueError("no_inventory")

    except HTTPException:
        raise  # Re-raise HTTP errors from smart allocation
    except Exception as e:
        if "no_inventory" not in str(e):
            logger.warning(f"Smart table allocation failed, using legacy: {e}")
        # Legacy fallback
        settings_row = db.table("restaurant_policies").select(
            "table_count, max_party_size"
        ).eq("restaurant_id", restaurant_id).execute()
        table_count = (settings_row.data[0].get("table_count") or 20) if settings_row.data else 20
        max_party = (settings_row.data[0].get("max_party_size") or 10) if settings_row.data else 10

        ok, cap_err = check_capacity(existing.data, booking_time, req.party_size, table_count, max_party)
        if not ok:
            raise HTTPException(status_code=409, detail=cap_err)

    user_row = db.table("user_sessions").select("name").eq("id", user_id).execute()
    customer_name = user_row.data[0]["name"] if user_row.data else "Guest"

    insert_data = {
        "restaurant_id": restaurant_id,
        "user_id": user_id,
        "customer_name": customer_name,
        "party_size": req.party_size,
        "booking_time": booking_time.isoformat(),
        "status": "confirmed",
        "special_requests": req.special_requests,
    }

    # Only add table assignment fields if they exist in DB
    if assigned_table_id:
        try:
            insert_data["assigned_table_id"] = assigned_table_id
            insert_data["assigned_table_number"] = assigned_table_number
        except Exception:
            pass

    result = db.table("bookings").insert(insert_data).execute()
    booking = result.data[0]

    if assigned_table_number:
        booking["message"] = f"Table {assigned_table_number} reserved for {req.party_size} guests."

    return booking


# ═══════════════════════════════════════════════════════════════════════════════
# FEEDBACK
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/feedback")
async def submit_feedback(
    req: FeedbackRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Submit feedback and immediately update CRM:
    - Stores the rating and comment
    - Updates average_rating on user_sessions
    - Updates tags (high raters get better service)
    - Logs last feedback details for staff CRM view
    """
    db = get_db()
    restaurant_id = req.restaurant_id or current_user.get("restaurant_id") or settings.default_restaurant_id
    user_id = current_user["user_id"]

    # Resolve user_id if needed
    user_data = db.table("user_sessions").select("*").eq("id", user_id).execute()
    if not user_data.data:
        by_name = db.table("user_sessions").select("*").eq(
            "restaurant_id", restaurant_id
        ).eq("name", current_user.get("name", "")).execute()
        if by_name.data:
            user_id = by_name.data[0]["id"]
            user_data = by_name
        else:
            raise HTTPException(status_code=404, detail="Session not found.")

    # Save feedback record
    feedback_result = db.table("feedback").insert({
        "restaurant_id": restaurant_id,
        "user_id": user_id,
        "ratings": json.dumps(req.order_ratings or {}),
        "overall_rating": req.overall_rating,
        "comments": req.comments,
    }).execute()

    # ── Update CRM with feedback data ─────────────────────────────────
    u = user_data.data[0]
    current_count = int(u.get("total_feedback_count") or 0)
    current_avg = float(u.get("average_rating") or 0)
    new_count = current_count + 1

    # Weighted rolling average
    new_avg = round(
        ((current_avg * current_count) + req.overall_rating) / new_count, 2
    )

    # Recompute tags including feedback-based ones
    visit_count = int(u.get("visit_count") or 0)
    total_spend = float(u.get("total_spend") or 0)
    base_tags = compute_tags(visit_count, total_spend, u.get("last_visit"))

    # Add loyalty tag for consistent high raters
    if new_avg >= 4.5 and new_count >= 3:
        if "Brand Ambassador" not in base_tags:
            base_tags.append("Brand Ambassador")
    if new_avg <= 2.5 and new_count >= 2:
        if "Needs Attention" not in base_tags:
            base_tags.append("Needs Attention")

    db.table("user_sessions").update({
        "average_rating": new_avg,
        "total_feedback_count": new_count,
        "last_feedback_rating": req.overall_rating,
        "last_feedback_comment": req.comments,
        "tags": base_tags,
    }).eq("id", user_id).execute()

    logger.info(
        f"Feedback saved: user={user_id} rating={req.overall_rating} "
        f"new_avg={new_avg} count={new_count}"
    )

    return {
        "detail": "Feedback submitted. Thank you!",
        "average_rating": new_avg,
        "feedback_count": new_count,
    }
    
class PartialCancelRequest(BaseModel):
    order_id: str
    cancel_type: str  # "full" | "partial"
    items_to_cancel: Optional[List[str]] = []  # item names to remove (for partial)


@app.post("/api/orders/cancel-request")
async def request_cancellation(
    req: PartialCancelRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Request cancellation of a full order or specific items within it.
    Always goes to kitchen for approval — never auto-cancels.
    """
    db = get_db()
    user_id = current_user["user_id"]
    restaurant_id = current_user.get("restaurant_id") or settings.default_restaurant_id

    order = db.table("orders").select("*").eq("id", req.order_id).execute()
    if not order.data:
        raise HTTPException(status_code=404, detail="Order not found.")
    o = order.data[0]

    if o.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Not your order.")

    if o.get("status") in ("completed", "cancelled"):
        raise HTTPException(
            status_code=409,
            detail="This order is already completed or cancelled."
        )

    if o.get("cancellation_status") == "requested":
        raise HTTPException(
            status_code=409,
            detail="A cancellation request is already pending for this order."
        )

    items_raw = o.get("items", "[]")
    if isinstance(items_raw, str):
        items_list = json.loads(items_raw)
    else:
        items_list = items_raw

    items_summary = ", ".join([
        f"{i.get('quantity', 1)}x {i.get('name', '')}" for i in items_list
    ])
    order_num = o.get("daily_order_number", "?")

    if req.cancel_type == "partial" and req.items_to_cancel:
        # Validate requested items exist in order
        order_item_names = [i.get("name", "").lower() for i in items_list]
        invalid = [
            item for item in req.items_to_cancel
            if item.lower() not in order_item_names
        ]
        if invalid:
            raise HTTPException(
                status_code=422,
                detail=f"Items not found in order: {', '.join(invalid)}"
            )

        cancel_desc = f"Remove: {', '.join(req.items_to_cancel)}"
    else:
        cancel_desc = "Full order cancellation"

    # Send to kitchen
    db.table("orders").update({
        "cancellation_status": "requested",
        "modification_text": cancel_desc,
    }).eq("id", req.order_id).execute()

    await manager.broadcast_to_kitchen(restaurant_id, "cancellation_request", {
        "order_id": req.order_id,
        "order_number": order_num,
        "customer_name": o.get("customer_name"),
        "table_number": o.get("table_number"),
        "items": items_list,
        "items_summary": items_summary,
        "cancel_type": req.cancel_type,
        "cancel_description": cancel_desc,
    })

    return {
        "detail": (
            f"Cancellation request sent to kitchen for Order #{order_num}. "
            f"Request: {cancel_desc}"
        )
    }
    
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
# CRM
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/staff/crm", dependencies=[Depends(require_staff)])
async def get_crm(current_user: dict = Depends(require_staff)):
    db = get_db()
    restaurant_id = current_user["restaurant_id"]

    result = (
        db.table("user_sessions")
        .select("*")
        .eq("restaurant_id", restaurant_id)
        .order("total_spend", desc=True)
        .execute()
    )
    customers = result.data

    # ── Compute restaurant-level ARPU ─────────────────────────────────────────
    total_revenue = sum(float(c.get("total_spend") or 0) for c in customers)
    paying_customers = [c for c in customers if float(c.get("total_spend") or 0) > 0]
    arpu = round(total_revenue / len(paying_customers), 2) if paying_customers else 0

    # ── Compute per-customer ARPU (revenue per visit) ─────────────────────────
    for c in customers:
        visits = int(c.get("visit_count") or 0)
        spend = float(c.get("total_spend") or 0)
        c["revenue_per_visit"] = round(spend / visits, 2) if visits > 0 else 0

    return {
        "customers": customers,
        "summary": {
            "total_customers": len(customers),
            "paying_customers": len(paying_customers),
            "total_revenue": round(total_revenue, 2),
            "arpu": arpu,  # Average Revenue Per User across restaurant
            "average_visits": round(
                sum(int(c.get("visit_count") or 0) for c in customers) / len(customers), 1
            ) if customers else 0,
        }
    }

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
# chat endpoint
# ═══════════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════════
# CHAT ENDPOINT — PASTE THIS ENTIRE BLOCK TO REPLACE YOUR EXISTING /api/chat
# ═══════════════════════════════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    message: str
    mode: str = "general"
    restaurant_id: Optional[str] = None
    table_number: Optional[str] = None
    conversation_history: list = []
    # State machine fields — stored in frontend sessionStorage, sent each request
    pending_action: Optional[str] = None       # "cancel_selection"|"mod_selection"|"mod_details"
    pending_order_id: Optional[str] = None
    pending_order_num: Optional[int] = None


@app.post("/api/chat")
async def chat(req: ChatRequest, current_user: dict = Depends(get_current_user)):
    db = get_db()

    # Staff tokens must not use the customer chat endpoint
    if current_user.get("role") in ("admin", "chef", "manager"):
        raise HTTPException(
            status_code=403,
            detail="Staff accounts cannot use the customer chat. Please use the customer portal."
        )

    restaurant_id = (
        current_user.get("restaurant_id")
        or req.restaurant_id
        or settings.default_restaurant_id
    )
    user_id = current_user["user_id"]

    logger.info(f"Chat: user={user_id} restaurant={restaurant_id} mode={req.mode} pending={req.pending_action}")

    # ── Resolve user_id against user_sessions ─────────────────────────────
    user_data = db.table("user_sessions").select(
        "id, allergies, name"
    ).eq("id", user_id).execute()

    if not user_data.data:
        by_name = db.table("user_sessions").select(
            "id, allergies, name"
        ).eq("restaurant_id", restaurant_id).eq(
            "name", current_user.get("name", "")
        ).execute()
        if by_name.data:
            user_id = by_name.data[0]["id"]
            user_data = by_name
            logger.info(f"Resolved user_id by name: {user_id}")
        else:
            raise HTTPException(
                status_code=404,
                detail="Session not found. Please log out and log back in."
            )

    allergies = (user_data.data[0].get("allergies") or []) if user_data.data else []
    customer_name = (user_data.data[0].get("name") or "Guest") if user_data.data else "Guest"

    # ── Fetch menu and settings ───────────────────────────────────────────
    menu = db.table("menu_items").select("*").eq("restaurant_id", restaurant_id).execute()
    settings_row = db.table("restaurant_policies").select(
        "ai_context"
    ).eq("restaurant_id", restaurant_id).execute()
    ai_context = (settings_row.data[0].get("ai_context") or "") if settings_row.data else ""

    # ── Always fetch active orders upfront (needed for cancel/modify) ─────
    active_orders_result = db.table("orders").select("*").eq(
        "user_id", user_id
    ).eq("restaurant_id", restaurant_id).in_(
        "status", ["pending", "preparing"]
    ).order("daily_order_number").execute()
    active_orders = active_orders_result.data or []

    # ── Run state machine ─────────────────────────────────────────────────
    from app.chat_service import process_chat
    try:
        result = await process_chat(
            message=req.message,
            mode=req.mode,
            restaurant_id=restaurant_id,
            table_number=req.table_number,
            menu_items=menu.data,
            customer_allergies=allergies,
            ai_context=ai_context,
            conversation_history=req.conversation_history,
            pending_action=req.pending_action,
            pending_order_id=req.pending_order_id,
            pending_order_num=req.pending_order_num,
            active_orders=active_orders,
        )
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")

    # ── Persist newly detected allergies ──────────────────────────────────
    if result.get("detected_allergies"):
        merged = list(set(allergies) | set(result["detected_allergies"]))
        db.table("user_sessions").update(
            {"allergies": merged}
        ).eq("id", user_id).execute()

    # ── Handle cancel requests (can be multiple orders) ───────────────────
    if result.get("action_type") == "cancel_request":
        target_orders = result.get("target_orders", [])
        for t in target_orders:
            order_id = t["order_id"]
            order_num = t["order_num"]
            items_summary = t["items_summary"]
            items_list = t["items_list"]

            # Check not already requested
            existing = db.table("orders").select(
                "cancellation_status, status"
            ).eq("id", order_id).execute()
            if existing.data:
                cur = existing.data[0]
                if cur.get("cancellation_status") == "requested":
                    continue
                if cur.get("status") in ("cancelled", "completed"):
                    continue

            db.table("orders").update(
                {"cancellation_status": "requested"}
            ).eq("id", order_id).execute()

            await manager.broadcast_to_kitchen(restaurant_id, "cancellation_request", {
                "order_id": order_id,
                "order_number": order_num,
                "customer_name": customer_name,
                "table_number": req.table_number,
                "items": items_list,
                "items_summary": items_summary,
            })
            logger.info(f"Cancellation requested: order #{order_num} id={order_id}")

    # ── Handle modification request (single order) ────────────────────────
    if result.get("action_type") == "mod_request":
        order_id = result.get("target_order_id")
        order_num = result.get("target_order_num")
        modification_text = result.get("modification_text", "")

        if order_id:
            existing = db.table("orders").select(
                "modification_status, status"
            ).eq("id", order_id).execute()
            if existing.data:
                cur = existing.data[0]
                if cur.get("modification_status") != "requested" and cur.get("status") not in ("cancelled", "completed"):
                    db.table("orders").update({
                        "modification_status": "requested",
                        "modification_text": modification_text,
                    }).eq("id", order_id).execute()

                    # Get full order for kitchen broadcast
                    full_order = db.table("orders").select("*").eq("id", order_id).execute()
                    items_list = []
                    items_summary = ""
                    if full_order.data:
                        items_list, items_summary = __import__(
                            "app.chat_service", fromlist=["get_items_summary"]
                        ).get_items_summary(full_order.data[0])

                    await manager.broadcast_to_kitchen(restaurant_id, "modification_request", {
                        "order_id": order_id,
                        "order_number": order_num,
                        "customer_name": customer_name,
                        "table_number": req.table_number,
                        "modification_text": modification_text,
                        "current_items": items_list,
                        "items_summary": items_summary,
                    })
                    logger.info(f"Modification requested: order #{order_num} id={order_id} — {modification_text}")

    # ── Auto-place order when AI mode is ordering ─────────────────────────
    msg_lower = req.message.lower().strip()
    is_question = msg_lower.endswith("?") or msg_lower.startswith((
        "what", "how", "do you", "is there", "can i", "menu", "show",
        "hi", "hello", "hey", "tell me", "list", "what's", "whats",
    )) or msg_lower.strip() in (
        "mains", "starters", "desserts", "drinks", "menu",
        "what do you have", "options", "specials",
    )

    # Never auto-order if this was a cancel/modify/state-machine message
    skip_order = (
        is_question
        or result.get("action_type") in ("cancel_request", "mod_request")
        or result.get("new_pending_action") is not None
        or req.pending_action is not None  # still in a state machine flow
    )

    mode_is_ordering = result.get("new_mode") == "ordering" or req.mode == "ordering"
    is_actual_order = mode_is_ordering and not skip_order and len(req.message.strip()) > 3

    if is_actual_order and req.table_number:
        logger.info(f"Attempting order: '{req.message}' table={req.table_number}")
        try:
            import json as _json
            from app.order_service import process_natural_language_order
            parsed = await process_natural_language_order(
                req.message, menu.data, allergies, ai_context
            )
            if parsed.items:
                daily_number = await get_next_order_number(db, restaurant_id)
                order_data = {
                    "restaurant_id": restaurant_id,
                    "user_id": user_id,
                    "customer_name": customer_name,
                    "table_number": req.table_number,
                    "items": _json.dumps([i.model_dump() for i in parsed.items]),
                    "price": parsed.total,
                    "status": "pending",
                    "cancellation_status": "none",
                    "modification_status": "none",
                    "allergy_warnings": parsed.allergy_warnings,
                    "daily_order_number": daily_number,
                }
                order_result = db.table("orders").insert(order_data).execute()
                order = order_result.data[0]
                await manager.broadcast_to_kitchen(restaurant_id, "new_order", {
                    "order_id": order["id"],
                    "order_number": daily_number,
                    "table_number": req.table_number,
                    "customer_name": customer_name,
                    "items": [i.model_dump() for i in parsed.items],
                    "total": parsed.total,
                    "allergy_warnings": parsed.allergy_warnings,
                })
                result["order_placed"] = True
                result["order_id"] = order["id"]
                result["order_total"] = parsed.total
                result["order_number"] = daily_number
                logger.info(f"Order #{daily_number} placed: {order['id']}")
            else:
                logger.info(f"No items parsed — unrecognized: {parsed.unrecognized_items}")
        except Exception as e:
            logger.warning(f"Auto-order failed: {e}")

    # ── Auto-create booking when AI says "I'll book that for you now" ─────
    # ── Auto-create booking when AI confirms ──────────────────────────────
    reply_lower = result.get("reply", "").lower()
    logger.info(f"Booking trigger — mode={result.get('new_mode')} reply='{result.get('reply','')[:80]}'")

    booking_trigger_phrases = [
        "i'll book that for you now",
        "please go to the book tab",
        "got it! please go to the book",
        "go to the book tab to confirm",
        "your reservation for",
    ]
    should_attempt_booking = (
        result.get("new_mode") == "booking"
        and any(phrase in reply_lower for phrase in booking_trigger_phrases)
        and not result.get("booking_placed")        # never try twice in one request
        and not result.get("booking_error")         # don't retry after an error
    )

    if should_attempt_booking:
        try:
            import re as _re
            from datetime import datetime as _dt, timedelta as _td
            from zoneinfo import ZoneInfo as _ZI
            from app.booking_service import validate_booking_time, check_capacity, check_duplicate_booking

            DUBAI_TZ = _ZI("Asia/Dubai")
            now_dubai = _dt.now(DUBAI_TZ)

            # ── Parse party size from conversation ────────────────────────
            # Use only current reply + current message — NOT full history
            # Full history causes old bookings to bleed into the parser
            parse_source = result.get("reply", "") + " " + req.message
            parse_lower = parse_source.lower()

            party_size = 2
            for pat in [
                r'\bfor\s+(\d+)\s*(?:people|guests|persons|pax)?\b',
                r'\b(\d+)\s*(?:people|guests|persons|pax)\b',
            ]:
                pm = _re.search(pat, parse_lower)
                if pm:
                    party_size = int(pm.group(1))
                    if 1 <= party_size <= 20:
                        break

            # ── Parse time from current reply ─────────────────────────────
            hour, minute = 19, 0
            tm = _re.search(r'\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b', parse_lower)
            if tm:
                hour = int(tm.group(1))
                minute = int(tm.group(2) or 0)
                if tm.group(3) == "pm" and hour != 12:
                    hour += 12
                elif tm.group(3) == "am" and hour == 12:
                    hour = 0

            # ── Parse date ONLY from current AI reply (not history) ───────
            # This is the critical fix — history contains old dates that bleed in
            date_source = result.get("reply", "")
            booking_date = None

            MONTHS = {
                "january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
                "july":7,"august":8,"september":9,"october":10,"november":11,"december":12,
                "jan":1,"feb":2,"mar":3,"apr":4,"jun":6,"jul":7,"aug":8,
                "sep":9,"oct":10,"nov":11,"dec":12,
            }
            WEEKDAYS = {
                "monday":0,"tuesday":1,"wednesday":2,"thursday":3,
                "friday":4,"saturday":5,"sunday":6,
                "mon":0,"tue":1,"wed":2,"thu":3,"fri":4,"sat":5,"sun":6,
            }

            import datetime as _datetime_mod

            def try_date(year, month, day):
                try:
                    return _datetime_mod.date(year, month, day)
                except ValueError:
                    return None

            ds = date_source.lower()

            # Pattern 1: "Month Day, Year" or "Month Day Year" e.g. "July 5 2026"
            matches = _re.findall(
                r'\b(january|february|march|april|may|june|july|august|september|'
                r'october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)'
                r'\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})\b', ds
            )
            if matches:
                # Take the LAST match — AI states the booking date last
                # e.g. "Today is April 9... I'll book April 11" → take April 11
                last = matches[-1]
                d = try_date(int(last[2]), MONTHS[last[0]], int(last[1]))
                if d:
                    booking_date = d

            # Pattern 2: "Day Month Year" e.g. "5 July 2026" or "5th July 2026"
            if not booking_date:
                matches2 = _re.findall(
                    r'\b(\d{1,2})(?:st|nd|rd|th)?\s+'
                    r'(january|february|march|april|may|june|july|august|september|'
                    r'october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)'
                    r'\s*,?\s*(\d{4})\b', ds
                )
                if matches2:
                    last2 = matches2[-1]
                    d = try_date(int(last2[2]), MONTHS[last2[1]], int(last2[0]))
                    if d:
                        booking_date = d

            # Pattern 3: "Month Day" no year — pick nearest future occurrence
            if not booking_date:
                matches3 = _re.findall(
                    r'\b(january|february|march|april|may|june|july|august|september|'
                    r'october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)'
                    r'\s+(\d{1,2})(?:st|nd|rd|th)?\b', ds
                )
                if matches3:
                    last3 = matches3[-1]
                    for yr in [now_dubai.year, now_dubai.year + 1]:
                        d = try_date(yr, MONTHS[last3[0]], int(last3[1]))
                        if d and d >= now_dubai.date():
                            booking_date = d
                            break

            # Pattern 4: "Day Month" no year
            if not booking_date:
                m = _re.search(
                    r'\b(\d{1,2})(?:st|nd|rd|th)?\s+'
                    r'(january|february|march|april|may|june|july|august|september|'
                    r'october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\b',
                    ds
                )
                if m:
                    for yr in [now_dubai.year, now_dubai.year + 1]:
                        d = try_date(yr, MONTHS[m.group(2)], int(m.group(1)))
                        if d and d >= now_dubai.date():
                            booking_date = d
                            break

            # Pattern 5: relative keywords — only from user message not AI reply
            user_msg_lower = req.message.lower()
            if not booking_date:
                if "today" in user_msg_lower:
                    booking_date = now_dubai.date()
                elif "tomorrow" in user_msg_lower:
                    booking_date = (now_dubai + _td(days=1)).date()
                else:
                    wm = _re.search(
                        r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|'
                        r'mon|tue|wed|thu|fri|sat|sun)\b', user_msg_lower
                    )
                    if wm:
                        twd = WEEKDAYS[wm.group(1)]
                        cwd = now_dubai.weekday()
                        days_ahead = (twd - cwd) % 7 or 7
                        booking_date = (now_dubai + _td(days=days_ahead)).date()

            if not booking_date:
                logger.warning("Could not parse booking date from AI reply")
                result["reply"] += (
                    "\n\n⚠️ I couldn't determine the date. "
                    "Please use the Book tab to confirm your reservation."
                )
                result["booking_error"] = True
                return result

            logger.info(f"Booking date resolved: {booking_date} hour={hour} min={minute}")

            booking_dt = _dt(
                booking_date.year, booking_date.month, booking_date.day,
                hour, minute, 0, tzinfo=DUBAI_TZ
            )

            # ── Validate time ─────────────────────────────────────────────
            valid, err = validate_booking_time(booking_dt)
            if not valid:
                result["reply"] = (
                    f"Sorry, I couldn't confirm that booking — {err}\n\n"
                    f"Please choose a different date and I'll book it for you."
                )
                result["booking_placed"] = False
                result["booking_error"] = True
                return result

            # ── Fetch existing bookings for this user only ────────────────
            user_bookings = db.table("bookings").select("*").eq(
                "restaurant_id", restaurant_id
            ).eq("user_id", user_id).execute()

            # ── Duplicate check: same user, ±2hr window, active only ──────
            is_dup = check_duplicate_booking(user_bookings.data, user_id, booking_dt)
            logger.info(f"Duplicate check: is_dup={is_dup} for {booking_dt.isoformat()}")

            if is_dup:
                result["reply"] = (
                    f"You already have a booking close to that time. "
                    f"Please choose a time at least 2 hours apart from your existing booking, "
                    f"or cancel it from the Book tab first."
                )
                result["booking_placed"] = False
                result["booking_error"] = True
                return result

            # ── Capacity check across all restaurant bookings ─────────────
            all_bookings = db.table("bookings").select("*").eq(
                "restaurant_id", restaurant_id
            ).execute()

            pol = db.table("restaurant_policies").select(
                "table_count, max_party_size"
            ).eq("restaurant_id", restaurant_id).execute()
            tc = (pol.data[0].get("table_count") or 20) if pol.data else 20
            mp = (pol.data[0].get("max_party_size") or 10) if pol.data else 10

            cap_ok, cap_err = check_capacity(all_bookings.data, booking_dt, party_size, tc, mp)
            if not cap_ok:
                result["reply"] = (
                    f"Sorry, no tables available at that time — {cap_err}\n\n"
                    f"Please choose a different time."
                )
                result["booking_placed"] = False
                result["booking_error"] = True
                return result

            # ── Create the booking ────────────────────────────────────────
            bk = db.table("bookings").insert({
                "restaurant_id": restaurant_id,
                "user_id": user_id,
                "customer_name": customer_name,
                "party_size": party_size,
                "booking_time": booking_dt.isoformat(),
                "status": "confirmed",
            }).execute()

            if bk.data:
                # Format date/time from the actual booking_dt — single source of truth
                time_str = booking_dt.strftime("%-I:%M %p") if hasattr(booking_dt, 'strftime') else booking_dt.strftime("%I:%M %p").lstrip("0")
                date_str = booking_dt.strftime("%A %d %B %Y")
                summary = f"{party_size} people · {date_str} · {time_str}"
                result["booking_placed"] = True
                result["booking_id"] = bk.data[0]["id"]
                result["booking_summary"] = summary
                # Include ISO string so frontend can format it correctly
                result["booking_datetime_iso"] = booking_dt.isoformat()
                logger.info(f"Booking created: {booking_dt.isoformat()} for {party_size} people")
            else:
                result["reply"] += "\n\n⚠️ Booking could not be saved. Please use the Book tab."
                result["booking_error"] = True

        except Exception as e:
            logger.error(f"Auto-booking failed: {e}", exc_info=True)
            result["booking_error"] = True

    return result

# ═══════════════════════════════════════════════════════════════════════════════
# QR CODE GENERATION
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/qr/{restaurant_id}")
async def get_qr_code(
    restaurant_id: str,
    table: Optional[str] = None,
    format: str = "png",          # png or html (html shows download page)
):
    """
    Generate a QR code for a specific restaurant (and optionally a table).
    Scan → opens customer login with restaurant_id + table pre-filled.
    """
    base_url = settings.allowed_origins.split(",")[0].strip()  # first origin = frontend URL
    url = f"{base_url}/customer/login?restaurant={restaurant_id}"
    if table:
        url += f"&table={table}"

    # Generate QR image
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    if format == "html":
        # Returns a simple HTML page staff can print
        import base64
        img_b64 = base64.b64encode(buf.getvalue()).decode()
        label = f"Table {table}" if table else "Restaurant QR"
        html = f"""
        <html><body style="text-align:center;font-family:sans-serif;padding:40px">
          <h2>{label}</h2>
          <img src="data:image/png;base64,{img_b64}" style="width:300px"/>
          <p style="font-size:12px;color:#888">{url}</p>
          <a href="data:image/png;base64,{img_b64}" download="qr_{restaurant_id}_{table or 'main'}.png">
            Download PNG
          </a>
        </body></html>
        """
        return HTMLResponse(content=html)

    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png",
        headers={"Content-Disposition": f"inline; filename=qr_{restaurant_id}.png"})

# ═══════════════════════════════════════════════════════════════════════════════
# VOICE TRANSCRIPTION (Whisper via Groq)
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/transcribe")
async def transcribe_voice(
    audio: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """
    Accepts an audio file (webm/mp4/wav), sends it to Groq Whisper,
    returns the transcribed text. Frontend pastes this into the chat input.
    """
    try:
        client = get_groq()
        audio_bytes = await audio.read()

        transcription = client.audio.transcriptions.create(
            model="whisper-large-v3",
            file=(audio.filename or "audio.webm", audio_bytes, audio.content_type or "audio/webm"),
            response_format="text",
        )
        return {"text": transcription}

    except Exception as e:
        logger.error(f"Transcription error: {e}")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")

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
