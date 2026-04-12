"""
staff_chat_service.py - AI assistant for restaurant staff.

Completely separate from the customer chatbot.
Staff AI can:
- Answer questions about bookings (busy dates, blackout dates)
- Show delayed/long-running kitchen orders
- Identify priority tables/customers
- Check which dishes are sold out
- Send messages to specific customers at their tables
- Give revenue and operational insights
"""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from groq import Groq
from app.config import settings

logger = logging.getLogger(__name__)
DUBAI_TZ = ZoneInfo("Asia/Dubai")


def format_orders_for_context(orders: list[dict]) -> str:
    if not orders:
        return "No active orders."
    lines = []
    now = datetime.now(DUBAI_TZ)
    for o in orders:
        try:
            created = datetime.fromisoformat(o["created_at"])
            if created.tzinfo is None:
                created = created.replace(tzinfo=DUBAI_TZ)
            mins_ago = int((now - created).total_seconds() / 60)
        except Exception:
            mins_ago = 0

        items_raw = o.get("items", [])
        if isinstance(items_raw, str):
            import json
            items_raw = json.loads(items_raw)
        items_str = ", ".join([
            f"{i.get('quantity',1)}x {i.get('name','')}" for i in items_raw
        ])
        lines.append(
            f"Order #{o.get('daily_order_number','?')} | Table {o.get('table_number','?')} "
            f"| {o.get('customer_name','?')} | {items_str} "
            f"| Status: {o.get('status','?')} | {mins_ago} min ago"
        )
    return "\n".join(lines)


def format_bookings_for_context(bookings: list[dict]) -> str:
    if not bookings:
        return "No upcoming bookings."
    lines = []
    for b in bookings:
        try:
            bt = datetime.fromisoformat(b["booking_time"])
            date_str = bt.strftime("%a %d %b %Y %I:%M %p")
        except Exception:
            date_str = b.get("booking_time", "?")
        lines.append(
            f"{date_str} | {b.get('party_size','?')} guests "
            f"| {b.get('customer_name','?')} | Status: {b.get('status','?')}"
        )
    return "\n".join(lines)


def format_menu_for_context(menu: list[dict]) -> str:
    available = [i for i in menu if not i.get("sold_out")]
    sold_out = [i for i in menu if i.get("sold_out")]
    lines = []
    if available:
        lines.append("AVAILABLE:")
        lines.extend([f"  - {i['name']} ({i['category']}) AED {i['price']}" for i in available])
    if sold_out:
        lines.append("SOLD OUT:")
        lines.extend([f"  - {i['name']} ({i['category']})" for i in sold_out])
    return "\n".join(lines) if lines else "No menu items."


def format_customers_for_context(customers: list[dict]) -> str:
    if not customers:
        return "No customers."
    lines = []
    for c in customers:
        tags = ", ".join(c.get("tags") or []) or "none"
        lines.append(
            f"{c.get('name','?')} | Table: {c.get('table_number') or 'not seated'} "
            f"| Visits: {c.get('visit_count',0)} | Spend: AED {float(c.get('total_spend',0)):.2f} "
            f"| Tags: {tags}"
        )
    return "\n".join(lines)


async def process_staff_chat(
    message: str,
    restaurant_id: str,
    staff_name: str,
    staff_role: str,
    active_orders: list[dict],
    bookings: list[dict],
    menu: list[dict],
    customers: list[dict],
    conversation_history: list[dict] = [],
    ai_context: str = "",
) -> dict:
    """
    Process a staff chat message with full operational context.
    Returns: { reply, action_type, action_data }
    action_type can be: None | "send_customer_message"
    """
    now = datetime.now(DUBAI_TZ)
    now_str = now.strftime("%A %d %B %Y, %I:%M %p (Dubai time)")

    # ── Build operational context ─────────────────────────────────────────────
    orders_context = format_orders_for_context(active_orders)
    bookings_context = format_bookings_for_context(bookings)
    menu_context = format_menu_for_context(menu)
    customers_context = format_customers_for_context(customers)

    # Identify delayed orders (>20 min in pending/preparing)
    delayed = []
    for o in active_orders:
        if o.get("status") not in ("pending", "preparing"):
            continue
        try:
            created = datetime.fromisoformat(o["created_at"])
            if created.tzinfo is None:
                created = created.replace(tzinfo=DUBAI_TZ)
            mins = int((now - created).total_seconds() / 60)
            if mins > 20:
                delayed.append(f"Order #{o.get('daily_order_number','?')} Table {o.get('table_number','?')} ({mins} min)")
        except Exception:
            pass

    delayed_context = "\n".join(delayed) if delayed else "None"

    # Compute booking density per date for next 7 days
    booking_counts: dict[str, int] = {}
    for b in bookings:
        if b.get("status") == "cancelled":
            continue
        try:
            bt = datetime.fromisoformat(b["booking_time"])
            date_key = bt.strftime("%Y-%m-%d")
            booking_counts[date_key] = booking_counts.get(date_key, 0) + 1
        except Exception:
            pass

    # Find busy dates (>5 bookings) and blackout-risk dates (>8 bookings)
    busy_dates = [d for d, c in booking_counts.items() if c >= 5]
    blackout_dates = [d for d, c in booking_counts.items() if c >= 8]

    # Priority customers: VIP or Big Spender currently seated
    priority = [
        c for c in customers
        if c.get("table_number")
        and any(t in (c.get("tags") or []) for t in ["VIP", "Big Spender", "Brand Ambassador"])
    ]
    priority_context = format_customers_for_context(priority) if priority else "None currently seated"

    # ── Detect if staff wants to send a message to a customer ────────────────
    send_msg_intent = any(phrase in message.lower() for phrase in [
        "send message", "tell table", "notify table", "message table",
        "send to table", "inform table", "alert table", "text table",
        "message customer", "send customer",
    ])

    system_prompt = f"""You are an intelligent AI assistant for restaurant staff.
You have full access to real-time restaurant operations data.

Current time: {now_str}
Staff member: {staff_name} ({staff_role})
{f"Restaurant notes: {ai_context}" if ai_context else ""}

═══ ACTIVE ORDERS ═══
{orders_context}

═══ DELAYED ORDERS (>20 min) ═══
{delayed_context}

═══ UPCOMING BOOKINGS ═══
{bookings_context}

═══ BUSY DATES (5+ bookings) ═══
{', '.join(busy_dates) if busy_dates else 'None in next 7 days'}

═══ BLACKOUT RISK DATES (8+ bookings) ═══
{', '.join(blackout_dates) if blackout_dates else 'None'}

═══ MENU ═══
{menu_context}

═══ PRIORITY CUSTOMERS SEATED ═══
{priority_context}

═══ ALL SEATED CUSTOMERS ═══
{customers_context}

YOUR CAPABILITIES:
1. Answer operational questions about orders, bookings, customers, menu
2. Identify delays, priority customers, busy periods
3. Give revenue insights (total active table revenue, ARPU)
4. To send a message to a specific table: respond with exactly this format at the END of your reply:
   SEND_TO_TABLE:[table_number]:[message to customer]
   Example: SEND_TO_TABLE:5:The kitchen will be closing in 30 minutes. Would you like to place any final orders?

RULES:
- Be concise and operational — staff are busy
- Always reference specific order/table numbers
- For "send message" requests, always include the SEND_TO_TABLE: line
- Never place orders or make bookings yourself — guide staff to do it
- Highlight urgent issues first
"""

    try:
        client = Groq(api_key=settings.groq_api_key)
        messages = conversation_history[-8:] + [{"role": "user", "content": message}]
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": system_prompt}] + messages,
            temperature=0.3,
            max_tokens=600,
        )
        reply = response.choices[0].message.content or "Sorry, I couldn't process that."
    except Exception as e:
        logger.error(f"Staff AI error: {e}")
        reply = "AI service unavailable. Please try again."
        return {"reply": reply, "action_type": None, "action_data": None}

    # ── Parse SEND_TO_TABLE action ────────────────────────────────────────────
    action_type = None
    action_data = None

    if "SEND_TO_TABLE:" in reply:
        import re
        match = re.search(r'SEND_TO_TABLE:([^:]+):(.+?)(?:\n|$)', reply, re.DOTALL)
        if match:
            table_num = match.group(1).strip()
            customer_msg = match.group(2).strip()
            action_type = "send_customer_message"
            action_data = {
                "table_number": table_num,
                "message": customer_msg,
            }
            # Clean the SEND_TO_TABLE line from the visible reply
            reply = reply.replace(match.group(0), "").strip()
            reply += f"\n\n📨 Message sent to Table {table_num}."

    return {
        "reply": reply,
        "action_type": action_type,
        "action_data": action_data,
    }
