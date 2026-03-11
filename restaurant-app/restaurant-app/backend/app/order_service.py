"""
order_service.py - AI-powered order processing engine.

Preserves ALL logic from the stable Telegram version:
  - Groq API (Llama 3.3 70B)
  - Fuzzy menu matching ("burger" → "Full Stack Burger")
  - Sold-out enforcement
  - Allergy detection & warnings
  - Deterministic pricing (unit_price × quantity)
  - Robust JSON extraction (handles code blocks, conversational filler, etc.)
"""

import json
import logging
import re
from typing import Optional

from groq import Groq

from app.config import settings
from app.models import AIOrderParseResponse, OrderItem

logger = logging.getLogger(__name__)

# ─── Groq client ──────────────────────────────────────────────────────────────

_groq_client: Optional[Groq] = None

def get_groq() -> Groq:
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=settings.groq_api_key)
    return _groq_client


# ─── Allergy detection ────────────────────────────────────────────────────────

ALLERGEN_PATTERNS = {
    "gluten":   r"\b(gluten|wheat|bread|flour|pasta|noodle|bun|wrap|roti|pita)\b",
    "dairy":    r"\b(milk|cheese|butter|cream|dairy|lactose|yogurt|ghee)\b",
    "nuts":     r"\b(nut|peanut|almond|cashew|walnut|pistachio|hazelnut)\b",
    "shellfish":r"\b(shrimp|prawn|crab|lobster|shellfish|scallop|mussel)\b",
    "eggs":     r"\b(egg|eggs|omelette|frittata)\b",
    "soy":      r"\b(soy|tofu|edamame|tempeh|miso)\b",
}


def detect_allergens_in_text(text: str) -> list[str]:
    """Scan menu item description/name for known allergens."""
    text_lower = text.lower()
    found = []
    for allergen, pattern in ALLERGEN_PATTERNS.items():
        if re.search(pattern, text_lower):
            found.append(allergen)
    return found


def check_allergy_warnings(
    items: list[OrderItem],
    customer_allergies: list[str],
    menu_items: list[dict],
) -> list[str]:
    """
    Cross-reference ordered items against customer's stated allergies.
    Returns human-readable warning strings.
    """
    if not customer_allergies:
        return []

    warnings = []
    menu_map = {item["name"].lower(): item for item in menu_items}

    for order_item in items:
        menu_entry = menu_map.get(order_item.name.lower())
        if not menu_entry:
            continue

        allergens_in_item = menu_entry.get("allergens", []) or detect_allergens_in_text(
            f"{menu_entry.get('name','')} {menu_entry.get('description','')}"
        )

        for customer_allergy in customer_allergies:
            if customer_allergy.lower() in [a.lower() for a in allergens_in_item]:
                warnings.append(
                    f"⚠️ {order_item.name} contains {customer_allergy} (allergy on file)"
                )
    return warnings


# ─── JSON extraction (robust) ─────────────────────────────────────────────────

def extract_json_from_text(text: str) -> Optional[dict]:
    """
    Extract a JSON object from AI output that may contain:
      - Markdown code fences: ```json{...}```
      - Conversational preamble: "Here is your order: {...}"
      - Raw JSON
    Returns parsed dict or None on failure.
    """
    # Method 1: code block
    code_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if code_block:
        try:
            return json.loads(code_block.group(1))
        except json.JSONDecodeError:
            pass

    # Method 2: outermost braces
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

    # Method 3: direct parse
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    logger.error(f"Could not extract JSON from AI output: {text[:200]}")
    return None


# ─── Fuzzy menu matching ──────────────────────────────────────────────────────

def build_menu_context(menu_items: list[dict]) -> str:
    """Format menu items for injection into the AI prompt."""
    lines = []
    for item in menu_items:
        status = " [SOLD OUT]" if item.get("sold_out") else ""
        lines.append(
            f"- {item['name']}{status} | {item['category']} | AED {item['price']:.2f}"
            + (f" | {item['description']}" if item.get("description") else "")
        )
    return "\n".join(lines)


# ─── Main order processing ────────────────────────────────────────────────────

async def process_natural_language_order(
    user_input: str,
    menu_items: list[dict],
    customer_allergies: list[str] = [],
    ai_context: str = "",
) -> AIOrderParseResponse:
    """
    Parse a free-text order into structured line items.

    Steps:
      1. Build prompt with full menu
      2. Call Groq (Llama 3.3 70B)
      3. Extract JSON robustly
      4. Validate items against live menu (sold-out, pricing)
      5. Check allergens
      6. Return structured response
    """
    menu_context = build_menu_context(menu_items)
    menu_names_lower = {item["name"].lower(): item for item in menu_items}

    system_prompt = f"""You are an AI waiter for a restaurant. Your job is to parse customer orders.

MENU:
{menu_context}

{f"RESTAURANT NOTES: {ai_context}" if ai_context else ""}

RULES:
1. Match items using fuzzy matching (e.g. "burger" → closest menu item)
2. NEVER include sold-out items in the order
3. Use exact menu prices — never guess
4. Return ONLY valid JSON in this exact format:
{{
  "items": [
    {{"name": "Full Stack Burger", "quantity": 2, "unit_price": 45.0, "total_price": 90.0}}
  ],
  "total": 90.0,
  "unrecognized_items": ["pizza"],
  "sold_out_items": ["Fish & Chips"]
}}

Do not add any explanation or preamble — JSON only."""

    try:
        client = get_groq()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Order: {user_input}"},
            ],
            temperature=0.1,  # Low temp for deterministic pricing
            max_tokens=800,
        )
        raw = response.choices[0].message.content or ""
        logger.info(f"Groq raw response: {raw[:300]}")

    except Exception as e:
        logger.error(f"Groq API error: {e}")
        raise ValueError(f"AI service unavailable: {e}")

    parsed = extract_json_from_text(raw)
    if not parsed:
        raise ValueError("Could not parse AI response. Please try rephrasing your order.")

    # ── Validate and re-price items from live menu ────────────────────────────
    # The AI can hallucinate prices. We always re-derive price from the real menu.
    validated_items: list[OrderItem] = []
    sold_out_items: list[str] = []

    for ai_item in parsed.get("items", []):
        name_lower = ai_item.get("name", "").lower()
        # Find best match in menu
        menu_entry = menu_names_lower.get(name_lower)
        if not menu_entry:
            # Try partial match
            for key, entry in menu_names_lower.items():
                if name_lower in key or key in name_lower:
                    menu_entry = entry
                    break

        if not menu_entry:
            parsed.setdefault("unrecognized_items", []).append(ai_item.get("name"))
            continue

        if menu_entry.get("sold_out"):
            sold_out_items.append(menu_entry["name"])
            continue

        qty = max(1, int(ai_item.get("quantity", 1)))
        unit_price = float(menu_entry["price"])  # Always use real price
        validated_items.append(OrderItem(
            name=menu_entry["name"],
            quantity=qty,
            unit_price=unit_price,
            total_price=round(unit_price * qty, 2),
        ))

    real_total = round(sum(i.total_price for i in validated_items), 2)

    # ── Allergy check ─────────────────────────────────────────────────────────
    warnings = check_allergy_warnings(validated_items, customer_allergies, menu_items)

    return AIOrderParseResponse(
        items=validated_items,
        total=real_total,
        allergy_warnings=warnings,
        unrecognized_items=parsed.get("unrecognized_items", []),
        sold_out_items=sold_out_items or parsed.get("sold_out_items", []),
    )


# ─── Order modification ───────────────────────────────────────────────────────

async def process_modification(
    modification_text: str,
    current_items: list[OrderItem],
    menu_items: list[dict],
) -> tuple[list[OrderItem], float]:
    """
    Process a modification request like "remove the fries".
    Only removals are supported (can't add after kitchen acknowledgment).
    Returns (updated_items, new_total).
    """
    items_context = "\n".join(
        [f"- {i.name} x{i.quantity} @ AED {i.unit_price}" for i in current_items]
    )

    system_prompt = """You are an AI waiter. A customer wants to modify their order.
Only removals are supported. Parse what they want to remove.

Return ONLY valid JSON:
{
  "remove": ["Full Stack Burger"]
}
"""
    try:
        client = get_groq()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Current order:\n{items_context}\n\nModification: {modification_text}"},
            ],
            temperature=0.1,
            max_tokens=200,
        )
        raw = response.choices[0].message.content or ""
    except Exception as e:
        raise ValueError(f"AI service error: {e}")

    parsed = extract_json_from_text(raw)
    to_remove = [r.lower() for r in (parsed or {}).get("remove", [])]

    updated = [
        item for item in current_items
        if item.name.lower() not in to_remove
    ]
    new_total = round(sum(i.total_price for i in updated), 2)
    return updated, new_total
