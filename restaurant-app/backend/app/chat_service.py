"""
chat_service.py - Stateful AI chat with strict mode isolation.

State machine for modify/cancel flows:
  IDLE          → detecting intent from free text
  AWAITING_MOD_SELECTION  → asked "which order to modify?", waiting for order number
  AWAITING_MOD_DETAILS    → got order number, asking "what change?"
  AWAITING_CANCEL_SELECTION → asked "which order to cancel?", waiting for order number

This prevents the AI from handling modify/cancel conversationally
and ensures every request goes through the backend, not the LLM.
"""

from enum import Enum
from groq import Groq
from app.config import settings
import logging
import re

logger = logging.getLogger(__name__)


class ChatMode(str, Enum):
    general  = "general"
    ordering = "ordering"
    booking  = "booking"


# ─── Intent keyword lists ─────────────────────────────────────────────────────

ORDER_KEYWORDS = [
    "order", "want", "have", "get me", "give me", "i'll have", "i will have",
    "bring me", "can i get", "burger", "pizza", "coffee", "salad", "chicken",
    "food", "eat", "drink", "hungry", "thirsty", "lemonade", "cola", "dessert",
]

BOOKING_KEYWORDS = [
    "book", "table", "reserve", "reservation", "tonight", "tomorrow",
    "guests", "people", "party of", "slot", "available",
]

CANCEL_KEYWORDS = [
    "cancel", "cancell", "remove my order", "delete my order",
    "don't want", "dont want", "forget my order", "never mind my order",
    "scratch my order", "stop my order",
]

MODIFY_KEYWORDS = [
    "modify", "change my order", "update my order", "edit my order",
    "remove from my order", "add to my order", "swap in my order",
    "modify order", "modification",
]

# Words that indicate the user is specifying a change ALONG WITH the order number
# e.g. "modify order #3 — remove fries" — detected as inline modification
INLINE_CHANGE_SEPARATORS = ["—", "-", ":", "to", "by", "and"]


def detect_mode(message: str, current_mode: ChatMode) -> ChatMode:
    msg = message.lower()
    if any(k in msg for k in BOOKING_KEYWORDS):
        return ChatMode.booking
    if any(k in msg for k in ORDER_KEYWORDS):
        return ChatMode.ordering
    return current_mode


def is_cancel_intent(message: str) -> bool:
    msg = message.lower()
    return any(phrase in msg for phrase in CANCEL_KEYWORDS)


def is_modify_intent(message: str) -> bool:
    msg = message.lower()
    return any(phrase in msg for phrase in MODIFY_KEYWORDS)


def extract_order_numbers(message: str) -> list[int]:
    """
    Extract ALL order numbers from a message.
    Handles: "order #3", "order 3", "#3", "orders 4, 5 and 6"
    Returns list of ints, empty if none found.
    """
    msg = message.lower()

    # Pattern: "order #3" or "order 3" or "#3" (preceded by space or start)
    matches = re.findall(r'order\s*#?(\d+)', msg)
    if matches:
        return [int(m) for m in matches]

    # Pattern: standalone "#3"
    hash_matches = re.findall(r'#(\d+)', msg)
    if hash_matches:
        return [int(m) for m in hash_matches]

    # Pattern: numbers after "cancel"/"modify" keyword — "cancel 4, 5 and 6"
    # But ONLY if message starts with cancel/modify to avoid false positives
    if any(msg.strip().startswith(k) for k in ['cancel', 'modify', 'order']):
        num_matches = re.findall(r'\b(\d+)\b', msg)
        if num_matches:
            return [int(m) for m in num_matches]

    return []


def extract_inline_change(message: str) -> str | None:
    """
    Extract the change description from inline format:
    "modify order #3 — remove the fries" → "remove the fries"
    "modify order #3: no cheese" → "no cheese"
    Returns None if no inline change found.
    """
    msg = message
    for sep in ["—", " - ", ": ", " to ", " by removing ", " by adding "]:
        if sep in msg:
            parts = msg.split(sep, 1)
            if len(parts) == 2 and parts[1].strip():
                return parts[1].strip()
    return None


def format_order_list(orders: list[dict], action: str = "modify") -> str:
    """Format a list of active orders for display in chat."""
    lines = [f"Which order would you like to {action}?\n"]
    for o in orders:
        items_raw = o.get("items", "[]")
        if isinstance(items_raw, str):
            import json
            items_list = json.loads(items_raw)
        else:
            items_list = items_raw
        items_summary = ", ".join([
            f"{i.get('quantity', 1)}x {i.get('name', '')}" for i in items_list
        ])
        num = o.get("daily_order_number", "?")
        status = o.get("status", "pending")
        lines.append(
            f"  Order #{num} — {items_summary} "
            f"(AED {float(o.get('price', 0)):.2f}) [{status}]"
        )
    lines.append(f'\nReply with the order number e.g. "{action} order #2"')
    return "\n".join(lines)


def get_items_summary(order: dict) -> tuple[list, str]:
    """Returns (items_list, human_readable_summary) from an order dict."""
    items_raw = order.get("items", "[]")
    if isinstance(items_raw, str):
        import json
        items_list = json.loads(items_raw)
    else:
        items_list = items_raw
    summary = ", ".join([
        f"{i.get('quantity', 1)}x {i.get('name', '')}" for i in items_list
    ])
    return items_list, summary


# ─── Main chat processor ──────────────────────────────────────────────────────

async def process_chat(
    message: str,
    mode: str,
    restaurant_id: str,
    table_number: str | None,
    menu_items: list,
    customer_allergies: list,
    ai_context: str = "",
    conversation_history: list = [],
    # Pending state passed from frontend sessionStorage via request
    pending_action: str | None = None,       # "cancel_selection" | "mod_selection" | "mod_details"
    pending_order_id: str | None = None,     # order id waiting for details
    pending_order_num: int | None = None,    # order number waiting for details
    active_orders: list = [],                # passed in from main.py (already queried)
) -> dict:
    """
    Process a chat message through the state machine.

    Returns a dict with:
      reply: str
      new_mode: str
      new_pending_action: str | None   ← frontend stores this in sessionStorage
      new_pending_order_id: str | None
      new_pending_order_num: int | None
      action_type: str | None  ("cancel_request" | "mod_request" | None)
      target_order_id: str | None
      target_order_num: int | None
      modification_text: str | None
      detected_allergies: list
    """

    current_mode = ChatMode(mode)
    msg_lower = message.lower().strip()

    result = {
        "reply": "",
        "new_mode": current_mode.value,
        "new_pending_action": None,
        "new_pending_order_id": None,
        "new_pending_order_num": None,
        "action_type": None,
        "target_order_id": None,
        "target_order_num": None,
        "modification_text": None,
        "detected_allergies": [],
    }

    # ── Step 1: Detect new allergens in message ───────────────────────────
    from app.order_service import detect_allergens_in_text
    newly_mentioned = detect_allergens_in_text(message)
    if newly_mentioned:
        customer_allergies = list(set(customer_allergies + newly_mentioned))
        result["detected_allergies"] = newly_mentioned

    # ─────────────────────────────────────────────────────────────────────
    # STATE: AWAITING MODIFICATION DETAILS
    # User previously selected an order to modify, now giving the change
    # ─────────────────────────────────────────────────────────────────────
    if pending_action == "mod_details" and pending_order_id:
        # The message IS the modification description — send to kitchen
        order = next((o for o in active_orders if o["id"] == pending_order_id), None)
        if not order:
            result["reply"] = "Sorry, I couldn't find that order anymore. It may have been completed."
            return result

        _, items_summary = get_items_summary(order)
        order_num = order.get("daily_order_number", pending_order_num or "?")

        result["reply"] = (
            f"Modification request sent to kitchen for Order #{order_num}: {items_summary}.\n\n"
            f"Your request: \"{message}\"\n\n"
            f"The chef will approve or reject shortly — you'll be notified here."
        )
        result["action_type"] = "mod_request"
        result["target_order_id"] = pending_order_id
        result["target_order_num"] = order_num
        result["modification_text"] = message
        # Clear pending state
        result["new_pending_action"] = None
        result["new_pending_order_id"] = None
        result["new_pending_order_num"] = None
        return result

    # ─────────────────────────────────────────────────────────────────────
    # STATE: AWAITING ORDER SELECTION (cancel or modify)
    # User was shown a list and needs to pick an order number
    # ─────────────────────────────────────────────────────────────────────
    if pending_action in ("cancel_selection", "mod_selection"):
        order_nums = extract_order_numbers(message)

        if not order_nums:
            # User typed something that isn't an order number — re-prompt
            action_word = "cancel" if pending_action == "cancel_selection" else "modify"
            result["reply"] = (
                f"Please specify the order number, e.g. \"{action_word} order #2\"\n\n"
                + format_order_list(active_orders, action_word)
            )
            # Keep pending state unchanged
            result["new_pending_action"] = pending_action
            return result

        # Find matching orders
        matched_orders = [
            o for o in active_orders
            if o.get("daily_order_number") in order_nums
        ]

        if not matched_orders:
            result["reply"] = (
                f"Order number(s) {order_nums} not found in your active orders.\n\n"
                + format_order_list(active_orders,
                    "cancel" if pending_action == "cancel_selection" else "modify")
            )
            result["new_pending_action"] = pending_action
            return result

        if pending_action == "cancel_selection":
            # Send ALL matched orders to kitchen for cancellation
            cancelled_summaries = []
            for order in matched_orders:
                items_list, items_summary = get_items_summary(order)
                order_num = order.get("daily_order_number", "?")
                cancelled_summaries.append(f"Order #{order_num} ({items_summary})")

            result["reply"] = (
                f"Cancellation request(s) sent to kitchen for:\n"
                + "\n".join(f"  • {s}" for s in cancelled_summaries)
                + "\n\nThe chef will approve or reject shortly — you'll be notified here."
            )
            result["action_type"] = "cancel_request"
            result["target_orders"] = [
                {
                    "order_id": o["id"],
                    "order_num": o.get("daily_order_number"),
                    "items_summary": get_items_summary(o)[1],
                    "items_list": get_items_summary(o)[0],
                }
                for o in matched_orders
            ]
            result["new_pending_action"] = None
            return result

        else:  # mod_selection
            if len(matched_orders) > 1:
                result["reply"] = (
                    "Please modify orders one at a time.\n\n"
                    + format_order_list(active_orders, "modify")
                )
                result["new_pending_action"] = "mod_selection"
                return result

            selected_order = matched_orders[0]
            order_id = selected_order["id"]
            _, items_summary = get_items_summary(selected_order)
            order_num = selected_order.get("daily_order_number", "?")

            # Check if inline change was provided e.g. "order #3 — remove fries"
            inline_change = extract_inline_change(message)
            if inline_change:
                # Have everything — send to kitchen now
                result["reply"] = (
                    f"Modification request sent to kitchen for Order #{order_num}: {items_summary}.\n\n"
                    f"Your request: \"{inline_change}\"\n\n"
                    f"The chef will approve or reject shortly — you'll be notified here."
                )
                result["action_type"] = "mod_request"
                result["target_order_id"] = order_id
                result["target_order_num"] = order_num
                result["modification_text"] = inline_change
                result["new_pending_action"] = None
                return result

            # No inline change — ask what the change is
            result["reply"] = (
                f"Got it — Order #{order_num}: {items_summary} (AED {float(selected_order.get('price', 0)):.2f}).\n\n"
                f"What change would you like to make?\n"
                f"(e.g. \"remove 1 pizza\", \"add a burger\", \"change to chicken\")"
            )
            result["new_pending_action"] = "mod_details"
            result["new_pending_order_id"] = order_id
            result["new_pending_order_num"] = order_num
            return result

    # ─────────────────────────────────────────────────────────────────────
    # IDLE STATE: Check for cancel/modify intent in fresh message
    # ─────────────────────────────────────────────────────────────────────

    # ── Booking cancel/modify intent — must be checked BEFORE order cancel/modify ──
    BOOKING_CANCEL_PHRASES = [
        "cancel booking", "cancel my booking", "cancel reservation",
        "cancel my reservation", "delete booking", "remove booking",
    ]
    BOOKING_MODIFY_PHRASES = [
        "modify booking", "change booking", "update booking",
        "reschedule", "change my reservation", "modify my reservation",
        "change reservation",
    ]

    if any(phrase in msg_lower for phrase in BOOKING_CANCEL_PHRASES):
        result["reply"] = (
            "To cancel a booking, please go to the **Book** tab where all your "
            "upcoming reservations are listed. Click the ✕ button next to the "
            "booking you want to cancel.\n\n"
            "Note: Cancellations must be made at least 4 hours before the booking time."
        )
        result["new_mode"] = "booking"
        return result

    if any(phrase in msg_lower for phrase in BOOKING_MODIFY_PHRASES):
        result["reply"] = (
            "To modify a booking, please cancel the existing one from the **Book** tab "
            "and create a new reservation with your preferred details.\n\n"
            "Just type your new booking details here and I'll set it up for you."
        )
        result["new_mode"] = "booking"
        return result

    # Cancel intent
    if is_cancel_intent(message):
        if not active_orders:
            result["reply"] = "You don't have any active orders to cancel."
            return result

        order_nums = extract_order_numbers(message)

        # ── Handle pending state: user answered "full" or "partial" ──────────
        if pending_action == "cancel_type_selection" and pending_order_id:
            order = next((o for o in active_orders if o["id"] == pending_order_id), None)
            if not order:
                result["reply"] = "Sorry, that order is no longer active."
                return result

            items_list, items_summary = get_items_summary(order)
            order_num = order.get("daily_order_number", pending_order_num or "?")

            if "full" in msg_lower or "whole" in msg_lower or "entire" in msg_lower or "all" in msg_lower:
                result["reply"] = (
                    f"Full cancellation request sent to kitchen for Order #{order_num}: {items_summary}.\n\n"
                    f"The chef will approve or reject shortly — you'll be notified here."
                )
                result["action_type"] = "cancel_request"
                result["target_orders"] = [{
                    "order_id": pending_order_id,
                    "order_num": order_num,
                    "items_summary": items_summary,
                    "items_list": items_list,
                    "cancel_type": "full",
                }]
                result["new_pending_action"] = None
                return result

            elif "partial" in msg_lower or "specific" in msg_lower or "some" in msg_lower or "dish" in msg_lower or "item" in msg_lower:
                # Ask which items
                item_lines = "\n".join([
                    f"  • {i.get('quantity',1)}x {i.get('name','')}"
                    for i in items_list
                ])
                result["reply"] = (
                    f"Which item(s) would you like to remove from Order #{order_num}?\n\n"
                    f"Current items:\n{item_lines}\n\n"
                    f"Type the name(s) e.g. \"remove the burger\" or \"remove pizza and lemonade\""
                )
                result["new_pending_action"] = "cancel_item_selection"
                result["new_pending_order_id"] = pending_order_id
                result["new_pending_order_num"] = order_num
                return result

            else:
                result["reply"] = (
                    f"Please reply with:\n"
                    f"  • **\"full\"** — cancel the entire order\n"
                    f"  • **\"partial\"** — remove specific items only"
                )
                result["new_pending_action"] = "cancel_type_selection"
                result["new_pending_order_id"] = pending_order_id
                result["new_pending_order_num"] = pending_order_num
                return result

        # ── Handle pending state: user specifying which items to remove ───────
        if pending_action == "cancel_item_selection" and pending_order_id:
            order = next((o for o in active_orders if o["id"] == pending_order_id), None)
            if not order:
                result["reply"] = "Sorry, that order is no longer active."
                return result

            items_list, items_summary = get_items_summary(order)
            order_num = order.get("daily_order_number", pending_order_num or "?")

            # Extract item names from message
            mentioned_items = []
            for item in items_list:
                item_name = item.get("name", "")
                if item_name.lower() in msg_lower or any(
                    word in item_name.lower()
                    for word in msg_lower.split()
                    if len(word) > 3
                ):
                    mentioned_items.append(item_name)

            if not mentioned_items:
                item_lines = "\n".join([
                    f"  • {i.get('quantity',1)}x {i.get('name','')}"
                    for i in items_list
                ])
                result["reply"] = (
                    f"I couldn't identify which items to remove. Please use the exact names:\n\n"
                    f"{item_lines}"
                )
                result["new_pending_action"] = "cancel_item_selection"
                result["new_pending_order_id"] = pending_order_id
                result["new_pending_order_num"] = pending_order_num
                return result

            cancel_desc = f"Remove: {', '.join(mentioned_items)}"
            result["reply"] = (
                f"Partial cancellation request sent to kitchen for Order #{order_num}.\n\n"
                f"Request: {cancel_desc}\n\n"
                f"The chef will approve or reject shortly — you'll be notified here."
            )
            result["action_type"] = "cancel_request"
            result["target_orders"] = [{
                "order_id": pending_order_id,
                "order_num": order_num,
                "items_summary": items_summary,
                "items_list": items_list,
                "cancel_type": "partial",
                "cancel_description": cancel_desc,
            }]
            result["new_pending_action"] = None
            return result

        # ── Fresh cancel intent — find order(s) ──────────────────────────────
        if order_nums:
            matched = [o for o in active_orders if o.get("daily_order_number") in order_nums]
            if not matched:
                result["reply"] = (
                    f"Order(s) {order_nums} not found.\n\n"
                    + format_order_list(active_orders, "cancel")
                )
                result["new_pending_action"] = "cancel_selection"
                return result
        elif len(active_orders) == 1:
            matched = active_orders
        else:
            result["reply"] = format_order_list(active_orders, "cancel")
            result["new_pending_action"] = "cancel_selection"
            return result

        if len(matched) > 1:
            # Multiple orders selected — all get full cancellation (no partial for bulk)
            summaries = []
            target_orders = []
            for order in matched:
                items_list, items_summary = get_items_summary(order)
                order_num = order.get("daily_order_number", "?")
                summaries.append(f"Order #{order_num} ({items_summary})")
                target_orders.append({
                    "order_id": order["id"],
                    "order_num": order_num,
                    "items_summary": items_summary,
                    "items_list": items_list,
                    "cancel_type": "full",
                })
            result["reply"] = (
                f"Full cancellation requests sent to kitchen for:\n"
                + "\n".join(f"  • {s}" for s in summaries)
                + "\n\nThe chef will approve or reject shortly."
            )
            result["action_type"] = "cancel_request"
            result["target_orders"] = target_orders
            result["new_pending_action"] = None
            return result

        # Single order — ask full or partial
        selected_order = matched[0]
        items_list, items_summary = get_items_summary(selected_order)
        order_num = selected_order.get("daily_order_number", "?")
        order_id = selected_order["id"]

        item_lines = "\n".join([
            f"  • {i.get('quantity',1)}x {i.get('name','')}"
            for i in items_list
        ])

        result["reply"] = (
            f"Order #{order_num}: {items_summary} (AED {float(selected_order.get('price',0)):.2f})\n\n"
            f"Would you like to:\n"
            f"  • **\"full\"** — cancel the entire order\n"
            f"  • **\"partial\"** — remove specific item(s) only\n\n"
            f"Current items:\n{item_lines}"
        )
        result["new_pending_action"] = "cancel_type_selection"
        result["new_pending_order_id"] = order_id
        result["new_pending_order_num"] = order_num
        return result

    # Modify intent
    if is_modify_intent(message):
        if not active_orders:
            result["reply"] = (
                "You don't have any active orders to modify.\n\n"
                "💡 Tip: To add more items, simply order them. "
                "To remove items entirely, type \"cancel order\"."
            )
            return result

        order_nums = extract_order_numbers(message)
        inline_change = extract_inline_change(message)

        # Check if user is trying to change quantity or add/remove dishes
        quantity_words = ["add", "more", "extra", "less", "fewer", "reduce", "increase", "remove", "delete"]
        is_quantity_change = any(w in msg_lower for w in quantity_words)

        if is_quantity_change:
            result["reply"] = (
                "Modifications are limited to special instructions per dish "
                "(e.g. \"no cheese\", \"extra spicy\", \"no onions\").\n\n"
                "For other changes:\n"
                "  • To **add items** — just place a new order\n"
                "  • To **remove items** — type \"cancel order\" and choose partial cancellation"
            )
            return result

        # From here, modification = dish notes only
        if order_nums:
            if len(order_nums) > 1:
                result["reply"] = (
                    "Please modify orders one at a time.\n\n"
                    + format_order_list(active_orders, "modify")
                )
                result["new_pending_action"] = "mod_selection"
                return result

            matched = [o for o in active_orders if o.get("daily_order_number") == order_nums[0]]
            if not matched:
                result["reply"] = (
                    f"Order #{order_nums[0]} not found.\n\n"
                    + format_order_list(active_orders, "modify")
                )
                result["new_pending_action"] = "mod_selection"
                return result

            selected_order = matched[0]
            order_id = selected_order["id"]
            items_list, items_summary = get_items_summary(selected_order)
            order_num = selected_order.get("daily_order_number", "?")

            if inline_change:
                result["reply"] = (
                    f"Special instruction request sent to kitchen for Order #{order_num}: {items_summary}.\n\n"
                    f"Note: \"{inline_change}\"\n\n"
                    f"The chef will approve or reject — you'll be notified here."
                )
                result["action_type"] = "mod_request"
                result["target_order_id"] = order_id
                result["target_order_num"] = order_num
                result["modification_text"] = inline_change
                return result

            # Ask for the instruction
            item_lines = "\n".join([
                f"  • {i.get('quantity',1)}x {i.get('name','')}"
                for i in items_list
            ])
            result["reply"] = (
                f"Order #{order_num}:\n{item_lines}\n\n"
                f"What special instruction would you like to add?\n"
                f"(e.g. \"no cheese on the burger\", \"extra spicy pizza\", \"no onions\")\n\n"
                f"Note: For adding/removing whole items, use the order or cancel options."
            )
            result["new_pending_action"] = "mod_details"
            result["new_pending_order_id"] = order_id
            result["new_pending_order_num"] = order_num
            return result

        if len(active_orders) == 1:
            selected_order = active_orders[0]
            order_id = selected_order["id"]
            items_list, items_summary = get_items_summary(selected_order)
            order_num = selected_order.get("daily_order_number", "?")
            item_lines = "\n".join([
                f"  • {i.get('quantity',1)}x {i.get('name','')}"
                for i in items_list
            ])
            result["reply"] = (
                f"Order #{order_num}:\n{item_lines}\n\n"
                f"What special instruction would you like to add?\n"
                f"(e.g. \"no cheese on the burger\", \"extra spicy\", \"gluten-free if possible\")"
            )
            result["new_pending_action"] = "mod_details"
            result["new_pending_order_id"] = order_id
            result["new_pending_order_num"] = order_num
            return result

        result["reply"] = format_order_list(active_orders, "modify")
        result["new_pending_action"] = "mod_selection"
        return result

    # ─────────────────────────────────────────────────────────────────────
    # NORMAL AI CHAT — ordering, booking, general
    # Only reaches here if no cancel/modify intent detected
    # ─────────────────────────────────────────────────────────────────────

    new_mode = detect_mode(message, current_mode)
    result["new_mode"] = new_mode.value

    menu_text = "\n".join([
        f"- {i['name']} | {i['category']} | AED {i['price']}"
        + (" [SOLD OUT]" if i.get("sold_out") else "")
        + (f" | {i['description']}" if i.get("description") else "")
        for i in menu_items
    ])

    if new_mode == ChatMode.ordering:
        system = f"""You are an AI waiter. Help the customer order food.

MENU:
{menu_text}

{f"RESTAURANT NOTES: {ai_context}" if ai_context else ""}

STRICT RULES:
1. NEVER confirm an order as placed — orders are placed by the system, not you.
2. NEVER say "order placed", "confirmed", "done", or similar — just say what they ordered and the price.
3. NEVER handle cancellations or modifications — tell the customer to type "cancel order" or "modify order".
4. Only recommend items that exist on the menu above.
5. If an item is marked [SOLD OUT] say it's unavailable and suggest alternatives.
6. Customer allergies on file: {', '.join(customer_allergies) if customer_allergies else 'none'}.
7. Keep responses short — max 3 sentences.

Your job: confirm what the customer wants and the total. Nothing else."""

    elif new_mode == ChatMode.booking:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        dubai_now = datetime.now(ZoneInfo("Asia/Dubai")).strftime("%I:%M %p, %d %B %Y")
        system = f"""You are a restaurant booking assistant.
Current Dubai time: {dubai_now}

Collect: party size, date, time. That's all.

Rules:
- As soon as you have party size, date, and time, respond with EXACTLY this format and nothing else:
  "I'll book that for you now. Reservation for [X] people on [Month] [Day] [YEAR] at [time]."
- ALWAYS include the 4-digit year in your response — never omit it.
- If the customer does not specify a year, use the nearest future date.
- Example: "I'll book that for you now. Reservation for 4 people on April 3 2026 at 12:00 PM."
- Never tell the customer a time is too soon or in the past — the system will validate this automatically.
- Never ask for confirmation.
- Never add extra sentences.
- If the customer only gives a time without a date, ask: "What date would you like?"
- If the customer only gives a date without a time, ask: "What time would you like?"
{f"Restaurant info: {ai_context}" if ai_context else ""}"""

    else:
        system = f"""You are a friendly restaurant AI concierge.
Answer questions about the restaurant, menu, hours, and policies.

MENU:
{menu_text}

{f"Restaurant info: {ai_context}" if ai_context else ""}

RULES:
1. NEVER place, cancel, or modify orders — tell customers to use the order flow.
2. If asked about cancelling or modifying, tell them to type "cancel order" or "modify order".
3. Keep responses concise — max 3 sentences."""

    client = Groq(api_key=settings.groq_api_key)
    messages = conversation_history[-6:] + [{"role": "user", "content": message}]

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "system", "content": system}] + messages,
        temperature=0.3,
        max_tokens=300,
    )
    reply = response.choices[0].message.content or "Sorry, I didn't catch that. Could you rephrase?"

    result["reply"] = reply
    return result
