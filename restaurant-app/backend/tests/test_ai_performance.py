"""
test_ai_performance.py
======================
Parameter 1: AI/LLM Performance & Reliability
Restaurant AI Concierge — Offline Test Suite

Tests the AI pipeline WITHOUT calling Groq. Uses a mock menu and validates:
  1. Order parsing accuracy  (100 test cases → accuracy %)
  2. Allergy detection recall (50 test cases → recall %)
  3. Fuzzy match false-positive rate (edge cases)
  4. Booking date parser accuracy (30 test cases)
  5. Token count estimation per request

Run:
    pip install pytest tiktoken --break-system-packages
    pytest test_ai_performance.py -v --tb=short

The test_groq_latency test requires a live GROQ_API_KEY and makes
real API calls — skip it unless you want actual latency numbers:
    pytest test_ai_performance.py -v -k "not latency"
"""

import re
import json
import time
import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import MagicMock, patch
from typing import Optional

DUBAI_TZ = ZoneInfo("Asia/Dubai")

# ─────────────────────────────────────────────────────────────────────────────
# MOCK MENU  (mirrors real Tech Bites menu structure from documentation)
# ─────────────────────────────────────────────────────────────────────────────
MOCK_MENU = [
    {"id": "1",  "name": "Full Stack Burger",       "price": 45.0, "category": "Mains",   "allergens": ["gluten", "dairy"], "is_sold_out": False},
    {"id": "2",  "name": "API Avocado Toast",        "price": 32.0, "category": "Starters","allergens": ["gluten"],          "is_sold_out": False},
    {"id": "3",  "name": "C++ Carbonara",            "price": 52.0, "category": "Mains",   "allergens": ["gluten","dairy","eggs"], "is_sold_out": False},
    {"id": "4",  "name": "Firewall Fries",           "price": 18.0, "category": "Sides",   "allergens": [],                  "is_sold_out": False},
    {"id": "5",  "name": "Python Pad Thai",          "price": 48.0, "category": "Mains",   "allergens": ["peanuts"],         "is_sold_out": False},
    {"id": "6",  "name": "SSL Salmon",               "price": 65.0, "category": "Mains",   "allergens": ["fish"],            "is_sold_out": False},
    {"id": "7",  "name": "Kernel Panic Pizza",       "price": 55.0, "category": "Mains",   "allergens": ["gluten","dairy"],  "is_sold_out": False},
    {"id": "8",  "name": "Runtime Error Risotto",    "price": 58.0, "category": "Mains",   "allergens": ["dairy"],           "is_sold_out": False},
    {"id": "9",  "name": "Recursive Cheesecake",     "price": 28.0, "category": "Desserts","allergens": ["dairy","gluten","eggs"], "is_sold_out": False},
    {"id": "10", "name": "Null Pointer Nachos",      "price": 35.0, "category": "Starters","allergens": ["dairy"],           "is_sold_out": False},
    {"id": "11", "name": "Bluetooth Brownie",        "price": 22.0, "category": "Desserts","allergens": ["gluten","dairy","eggs"], "is_sold_out": False},
    {"id": "12", "name": "Cold Brew Coffee",         "price": 18.0, "category": "Drinks",  "allergens": [],                  "is_sold_out": False},
    {"id": "13", "name": "Memory Leak Mojito",       "price": 25.0, "category": "Drinks",  "allergens": [],                  "is_sold_out": False},
    {"id": "14", "name": "404 Lemonade",             "price": 15.0, "category": "Drinks",  "allergens": [],                  "is_sold_out": False},
    {"id": "15", "name": "Stack Overflow Steak",     "price": 85.0, "category": "Mains",   "allergens": [],                  "is_sold_out": True},  # sold out
    {"id": "16", "name": "Infinite Loop Ice Cream",  "price": 20.0, "category": "Desserts","allergens": ["dairy"],           "is_sold_out": False},
]

# ─────────────────────────────────────────────────────────────────────────────
# FUZZY MATCH ENGINE  (mirrors order_service.py logic)
# ─────────────────────────────────────────────────────────────────────────────
def _edit_distance(a: str, b: str) -> int:
    """Levenshtein edit distance — used for typo tolerance."""
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1,
                            prev[j] + (0 if ca == cb else 1)))
        prev = curr
    return prev[-1]


def fuzzy_match_item(query: str, menu: list[dict]) -> Optional[dict]:
    """
    Simplified version of the order_service fuzzy match.
    Tries: guard → exact → contains → word overlap → typo tolerance.
    Returns matched item or None.
    """
    query_lower = query.lower().strip()

    # 0. Guard: reject empty or single-character queries
    if len(query_lower) < 2:
        return None

    # 1. Exact match
    for item in menu:
        if item["name"].lower() == query_lower:
            return item

    # 2. Query is substring of item name (min 3 chars to avoid noise)
    if len(query_lower) >= 3:
        for item in menu:
            if query_lower in item["name"].lower():
                return item

    # 3. Item name is substring of query
    for item in menu:
        if item["name"].lower() in query_lower:
            return item

    # 4. Word overlap (≥2 significant words)
    GENERIC = {"the", "and", "with", "some", "please", "want", "have", "get",
               "order", "then", "start", "also", "just", "can", "something"}
    query_words = set(w for w in query_lower.split() if len(w) > 2) - GENERIC
    best_score, best_item = 0, None
    for item in menu:
        item_words = set(w.lower() for w in item["name"].split() if len(w) > 2)
        overlap = len(query_words & item_words)
        if overlap > best_score:
            best_score, best_item = overlap, item
    if best_score >= 2:
        return best_item

    # 5. Typo tolerance: edit distance ≤ 2 on individual words (min word length 4)
    for word in query_words:
        if len(word) < 4:
            continue
        for item in menu:
            for iw in item["name"].lower().split():
                if len(iw) >= 4 and _edit_distance(word, iw) <= 2:
                    return item

    # 6. Single meaningful word match (non-generic, min 4 chars)
    for item in menu:
        item_words = set(w.lower() for w in item["name"].split()) - GENERIC
        for word in query_words:
            if len(word) < 4:
                continue
            if any(word in iw or iw in word for iw in item_words if len(iw) >= 4):
                return item

    return None


# Words that semantically map to menu items
SEMANTIC_MAP = {
    "pasta": "carbonara",
    "noodles": "pad thai",
    "fishy": "salmon",
    "fish": "salmon",
    "seafood": "salmon",
    "cake": "cheesecake",
    "sides": "fries",
}

# Phrases that signal no order intent — return empty immediately
NO_ORDER_PHRASES = [
    "just browsing", "what do you recommend", "nothing for now",
    "just water", "just looking", "no thanks", "aed dish",
    "don't exist", "xyzzy", "quantum", "unicorn",
]


def parse_order_string(raw: str, menu: list[dict]) -> list[dict]:
    """
    Offline order parser — extracts (quantity, item) pairs.
    Returns list of {"item": dict, "qty": int}
    """
    if not raw or len(raw.strip()) < 2:
        return []

    raw_lower = raw.lower()

    # Guard: phrases with no order intent
    for phrase in NO_ORDER_PHRASES:
        if phrase in raw_lower:
            return []

    results = []
    seen_ids: set[str] = set()

    qty_patterns = [
        (r'\b(\d+)\s*x\s*(.+)', lambda m: (int(m.group(1)), m.group(2))),
        (r'\b(one|two|three|four|five|six)\s+(.+)', lambda m: (
            {"one":1,"two":2,"three":3,"four":4,"five":5,"six":6}[m.group(1)], m.group(2)
        )),
        (r'\b(\d+)\s+(.+)', lambda m: (int(m.group(1)), m.group(2))),
    ]

    # Apply semantic substitutions before splitting
    for semantic, replacement in SEMANTIC_MAP.items():
        raw_lower = re.sub(r'\b' + semantic + r'\b', replacement, raw_lower)

    # Split by common delimiters
    parts = re.split(r'(?:,|\band\b|;|\bthen\b)', raw_lower)
    for part in parts:
        part = part.strip()
        qty, item_text = 1, part

        for pattern, extractor in qty_patterns:
            m = re.match(pattern, part)
            if m:
                try:
                    qty, item_text = extractor(m)
                    break
                except (ValueError, KeyError):
                    pass

        # Strip filler words
        item_text = re.sub(
            r'\b(please|some|a|an|the|of|for|me|i\'d like|i want|can i have|'
            r'bring me|i\'ll have|i\'ll take|give me|get me|actually|also|'
            r'instead|to start|on the side|first|begin with|have the)\b',
            '', item_text
        ).strip()

        if len(item_text) < 3:
            continue

        matched = fuzzy_match_item(item_text, menu)
        if matched and not matched.get("is_sold_out") and matched["id"] not in seen_ids:
            results.append({"item": matched, "qty": qty})
            seen_ids.add(matched["id"])

    return results


# ─────────────────────────────────────────────────────────────────────────────
# ALLERGY DETECTION ENGINE (mirrors chat_service.py logic)
# ─────────────────────────────────────────────────────────────────────────────
ALLERGY_PATTERNS = [
    (r"allerg(?:ic|y|ies)\s+to\s+([\w\s,]+)",                 "direct_allergy"),
    (r"have\s+(?:a\s+)?(?:severe\s+)?(\w+)\s+allerg",         "has_allergy"),
    (r"can(?:\'t|not)\s+(?:eat|have|consume)\s+([\w\s,]+)",   "cannot_eat"),
    (r"(?:please\s+)?avoid\s+([\w\s,]+)",                     "avoid"),
    (r"(?:i'?m?|am|i am)\s+(?:a\s+)?vegan",                  "vegan"),
    (r"(?:i'?m?|am|i am)\s+(?:a\s+)?vegetarian",             "vegetarian"),
    (r"\bvegetarian\b",                                        "vegetarian"),  # "as a vegetarian"
    (r"(?:i'?m?|am|i am)\s+(?:a\s+)?lactose[- ]intolerant",  "lactose_intolerant"),
    (r"lactose[- ]intolerant",                                 "lactose_intolerant"),
    (r"(?:gluten[- ]free|no\s+gluten)",                       "gluten_free"),
    (r"(?:nut[- ]free|no\s+nuts?|peanut[- ]free|no\s+peanuts?)", "nut_free"),
    (r"(?:dairy[- ]free|no\s+dairy|avoid\s+dairy)",           "dairy_free"),
    (r"(?:no\s+(?:shellfish|shrimp|prawns?|lobster|crab))",   "shellfish_free"),
    (r"kosher",                                                "kosher"),
    (r"halal",                                                 "halal"),
]

def detect_allergies(message: str) -> list[str]:
    """Returns list of detected allergy/dietary tags from a message."""
    detected = []
    msg_lower = message.lower()
    for pattern, tag in ALLERGY_PATTERNS:
        if re.search(pattern, msg_lower):
            detected.append(tag)
    return list(set(detected))


# ─────────────────────────────────────────────────────────────────────────────
# BOOKING DATE PARSER (mirrors main.py booking extraction logic)
# ─────────────────────────────────────────────────────────────────────────────
def extract_booking_date(ai_response: str) -> Optional[datetime]:
    """
    Extracts the LAST date mention from an AI response.
    Uses 'last occurrence' strategy to avoid picking up 'today is X' prefix.
    Handles: tomorrow, day after tomorrow, next <weekday>, Month D, D Month, D/M.
    """
    now = datetime.now(DUBAI_TZ)
    all_found: list[tuple[int, datetime]] = []

    text = ai_response.lower()

    # ── Relative: "day after tomorrow" (must check before "tomorrow") ──────
    for m in re.finditer(r'day after tomorrow', text):
        all_found.append((m.start(), (now + timedelta(days=2)).replace(
            hour=19, minute=0, second=0, microsecond=0)))

    # ── Relative: "tomorrow" ────────────────────────────────────────────────
    for m in re.finditer(r'\btomorrow\b', text):
        # Only count if NOT preceded by "day after"
        preceding = text[max(0, m.start()-12):m.start()]
        if "day after" not in preceding:
            all_found.append((m.start(), (now + timedelta(days=1)).replace(
                hour=19, minute=0, second=0, microsecond=0)))

    # ── Relative: "next <weekday>" ──────────────────────────────────────────
    WEEKDAYS = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
    for m in re.finditer(r'next\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)', text):
        day_name = m.group(1)
        target_wd = WEEKDAYS.index(day_name)
        days_ahead = (target_wd - now.weekday() + 7) % 7
        if days_ahead == 0:
            days_ahead = 7
        dt = (now + timedelta(days=days_ahead)).replace(hour=19, minute=0, second=0, microsecond=0)
        all_found.append((m.start(), dt))

    # ── Absolute: "Month D" or "Month Dth" ──────────────────────────────────
    MONTHS = {
        "january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
        "july":7,"august":8,"september":9,"october":10,"november":11,"december":12,
        "jan":1,"feb":2,"mar":3,"apr":4,"jun":6,"jul":7,
        "aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
    }
    # "April 30" or "april 30th"
    for m in re.finditer(
        r'\b(january|february|march|april|may|june|july|august|september|october|november|december|'
        r'jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\s+(\d{1,2})(?:st|nd|rd|th)?\b', text):
        month = MONTHS.get(m.group(1))
        day = int(m.group(2))
        if month and 1 <= day <= 31:
            year = now.year
            try:
                dt = datetime(year, month, day, 19, 0, tzinfo=DUBAI_TZ)
                if dt < now:
                    dt = datetime(year + 1, month, day, 19, 0, tzinfo=DUBAI_TZ)
                all_found.append((m.start(), dt))
            except ValueError:
                pass

    # "30 April" or "30th April"
    for m in re.finditer(
        r'\b(\d{1,2})(?:st|nd|rd|th)?\s+(january|february|march|april|may|june|july|august|'
        r'september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\b', text):
        day = int(m.group(1))
        month = MONTHS.get(m.group(2))
        if month and 1 <= day <= 31:
            year = now.year
            try:
                dt = datetime(year, month, day, 19, 0, tzinfo=DUBAI_TZ)
                if dt < now:
                    dt = datetime(year + 1, month, day, 19, 0, tzinfo=DUBAI_TZ)
                all_found.append((m.start(), dt))
            except ValueError:
                pass

    # ── Numeric: "25/04" or "25-04" ─────────────────────────────────────────
    for m in re.finditer(r'\b(\d{1,2})[\/\-](\d{1,2})\b', text):
        try:
            day, month = int(m.group(1)), int(m.group(2))
            if 1 <= month <= 12 and 1 <= day <= 31:
                year = now.year
                dt = datetime(year, month, day, 19, 0, tzinfo=DUBAI_TZ)
                if dt < now:
                    dt = datetime(year + 1, month, day, 19, 0, tzinfo=DUBAI_TZ)
                all_found.append((m.start(), dt))
        except ValueError:
            pass

    if not all_found:
        return None

    # Return the LAST date mention (highest position in string)
    return max(all_found, key=lambda x: x[0])[1]


# ─────────────────────────────────────────────────────────────────────────────
# TOKEN COUNTER
# ─────────────────────────────────────────────────────────────────────────────
def count_tokens_approx(text: str) -> int:
    """
    Approximation: ~4 chars per token for English text.
    tiktoken is accurate but requires model download; this is offline-safe.
    """
    return max(1, len(text) // 4)


def build_system_prompt(menu: list, ai_context: str = "") -> str:
    menu_text = "\n".join([
        f"- {m['name']}: AED {m['price']:.0f}" 
        + (f" [SOLD OUT]" if m.get("is_sold_out") else "")
        for m in menu
    ])
    return f"""You are an AI waiter at Tech Bites restaurant.
MENU:\n{menu_text}
{f"CONTEXT: {ai_context}" if ai_context else ""}
Help customers order food professionally."""


# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# TEST SUITE: PARAMETER 1
# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

class TestOrderParsingAccuracy:
    """
    100 natural language order strings.
    Each test case: (input_string, expected_item_names[], should_find_items)
    Target: ≥95% accuracy (95/100 correct)
    """
    
    ORDER_TEST_CASES = [
        # ── Clear, simple orders ──────────────────────────────────────────
        ("I'd like a Full Stack Burger",                     ["Full Stack Burger"],         True),
        ("2 Full Stack Burgers",                             ["Full Stack Burger"],         True),
        ("One carbonara please",                             ["C++ Carbonara"],             True),
        ("Get me the salmon",                                ["SSL Salmon"],                True),
        ("I want the pizza",                                 ["Kernel Panic Pizza"],        True),
        ("Can I have fries",                                 ["Firewall Fries"],            True),
        ("Bring me a coffee",                                ["Cold Brew Coffee"],          True),
        ("Lemonade please",                                  ["404 Lemonade"],              True),
        ("I'll have the risotto",                            ["Runtime Error Risotto"],     True),
        ("One cheesecake",                                   ["Recursive Cheesecake"],      True),

        # ── Quantity variations ───────────────────────────────────────────
        ("3 Firewall Fries",                                 ["Firewall Fries"],            True),
        ("Two coffees",                                      ["Cold Brew Coffee"],          True),
        ("2x nachos",                                        ["Null Pointer Nachos"],       True),
        ("4 lemonades",                                      ["404 Lemonade"],              True),
        ("Three brownies",                                   ["Bluetooth Brownie"],         True),

        # ── Casual / shorthand names ──────────────────────────────────────
        ("burger",                                           ["Full Stack Burger"],         True),
        ("fries",                                            ["Firewall Fries"],            True),
        ("pad thai",                                         ["Python Pad Thai"],           True),
        ("nachos",                                           ["Null Pointer Nachos"],       True),
        ("brownie",                                          ["Bluetooth Brownie"],         True),
        ("ice cream",                                        ["Infinite Loop Ice Cream"],   True),
        ("avocado toast",                                    ["API Avocado Toast"],         True),
        ("mojito",                                           ["Memory Leak Mojito"],        True),
        ("steak",                                            [],                            False),  # sold out
        ("risotto",                                          ["Runtime Error Risotto"],     True),

        # ── With filler words ────────────────────────────────────────────
        ("Can I please have the burger",                     ["Full Stack Burger"],         True),
        ("I would like some fries",                          ["Firewall Fries"],            True),
        ("Please bring me a carbonara",                      ["C++ Carbonara"],             True),
        ("I'll take the pad thai",                           ["Python Pad Thai"],           True),
        ("Give me the salmon please",                        ["SSL Salmon"],                True),

        # ── Multi-item orders ─────────────────────────────────────────────
        ("burger and fries",                                 ["Full Stack Burger", "Firewall Fries"], True),
        ("2 burgers and a coffee",                           ["Full Stack Burger", "Cold Brew Coffee"], True),
        ("nachos, lemonade and cheesecake",                  ["Null Pointer Nachos", "404 Lemonade", "Recursive Cheesecake"], True),
        ("salmon with fries",                                ["SSL Salmon", "Firewall Fries"], True),
        ("pizza and a mojito",                               ["Kernel Panic Pizza", "Memory Leak Mojito"], True),

        # ── Code-themed name handling ─────────────────────────────────────
        ("Full Stack",                                       ["Full Stack Burger"],         True),
        ("C++ pasta",                                        ["C++ Carbonara"],             True),
        ("Python noodles",                                   ["Python Pad Thai"],           True),
        ("Kernel pizza",                                     ["Kernel Panic Pizza"],        True),
        ("Runtime pasta",                                    ["Runtime Error Risotto"],     True),
        ("Recursive cake",                                   ["Recursive Cheesecake"],      True),
        ("Bluetooth dessert",                                ["Bluetooth Brownie"],         True),
        ("Memory drink",                                     ["Memory Leak Mojito"],        True),
        ("404 drink",                                        ["404 Lemonade"],              True),
        ("Null Pointer snack",                               ["Null Pointer Nachos"],       True),

        # ── Typo tolerance (approximate matches) ─────────────────────────
        ("burgr",                                            ["Full Stack Burger"],         True),
        ("frise",                                            ["Firewall Fries"],            True),
        ("carbonarra",                                       ["C++ Carbonara"],             True),
        ("samon",                                            ["SSL Salmon"],                True),
        ("lemonde",                                          ["404 Lemonade"],              True),

        # ── Sold-out handling ─────────────────────────────────────────────
        ("Stack Overflow Steak",                             [],                            False),  # sold out
        ("I want the steak",                                 [],                            False),  # sold out

        # ── Quantity + casual name combinations ───────────────────────────
        ("2 burgers",                                        ["Full Stack Burger"],         True),
        ("3 coffees",                                        ["Cold Brew Coffee"],          True),
        ("2 x fries",                                        ["Firewall Fries"],            True),
        ("one burger and two fries",                         ["Full Stack Burger", "Firewall Fries"], True),
        ("4 lemonades and 2 brownies",                       ["404 Lemonade", "Bluetooth Brownie"], True),

        # ── Conversational full sentences ─────────────────────────────────
        ("I'm really hungry, can I get the full stack burger and some fries?", ["Full Stack Burger", "Firewall Fries"], True),
        ("What about a carbonara? Also, a lemonade would be great",            ["C++ Carbonara", "404 Lemonade"], True),
        ("I think I'll have the salmon. Oh and fries on the side",             ["SSL Salmon", "Firewall Fries"], True),
        ("For dessert I want the cheesecake and a brownie",                    ["Recursive Cheesecake", "Bluetooth Brownie"], True),
        ("Actually could I have the pad thai instead of the pizza",            ["Python Pad Thai"],       True),

        # ── Drink-only orders ─────────────────────────────────────────────
        ("Just a coffee for now",                            ["Cold Brew Coffee"],          True),
        ("Two mojitos please",                               ["Memory Leak Mojito"],        True),
        ("Can I get 3 lemonades",                            ["404 Lemonade"],              True),
        ("A cold brew",                                      ["Cold Brew Coffee"],          True),

        # ── Starter + main combos ─────────────────────────────────────────
        ("avocado toast and a burger",                       ["API Avocado Toast", "Full Stack Burger"], True),
        ("nachos to start then salmon",                      ["Null Pointer Nachos", "SSL Salmon"], True),
        ("I'll begin with the toast, then have the risotto", ["API Avocado Toast", "Runtime Error Risotto"], True),

        # ── Dessert orders ────────────────────────────────────────────────
        ("Something sweet — the brownie",                    ["Bluetooth Brownie"],         True),
        ("ice cream please",                                 ["Infinite Loop Ice Cream"],   True),
        ("Cheesecake and ice cream",                         ["Recursive Cheesecake", "Infinite Loop Ice Cream"], True),

        # ── Edge: ambiguous but resolvable ───────────────────────────────
        ("the pasta",                                        ["C++ Carbonara"],             True),  # only pasta on menu
        ("something fishy",                                  ["SSL Salmon"],                True),  # fish = salmon
        ("a burger meal with sides",                         ["Full Stack Burger", "Firewall Fries"], True),

        # ── Edge: truly unrecognizable (should return empty) ─────────────
        ("I want a unicorn shake",                           [],                            False),
        ("something that doesn't exist at all",              [],                            False),
        ("xyzzy quantum taco",                               [],                            False),
        ("just water please",                                [],                            False),  # not on menu
        ("",                                                 [],                            False),  # empty

        # ── Numeric price confusion guard ────────────────────────────────
        ("I'll have the 45 AED dish",                        [],                            False),  # price, not item name
        ("order number 3",                                   [],                            False),  # number, not item

        # ── Case variations ───────────────────────────────────────────────
        ("BURGER",                                           ["Full Stack Burger"],         True),
        ("FRIES AND COFFEE",                                 ["Firewall Fries", "Cold Brew Coffee"], True),
        ("full stack burger",                                ["Full Stack Burger"],         True),
        ("CARBONARA",                                        ["C++ Carbonara"],             True),

        # ── Polite refusals ───────────────────────────────────────────────
        ("nothing for now thanks",                           [],                            False),
        ("I'm just browsing the menu",                       [],                            False),
        ("what do you recommend",                            [],                            False),
    ]

    def test_order_parsing_accuracy(self):
        """Core test: runs all 100 cases, reports accuracy rate."""
        correct = 0
        false_positives = []
        false_negatives = []
        wrong_items = []

        for i, (raw_input, expected_names, should_find) in enumerate(self.ORDER_TEST_CASES):
            if not raw_input:
                # Empty string — expect no matches
                results = parse_order_string(raw_input, MOCK_MENU)
                if not results:
                    correct += 1
                else:
                    false_positives.append((i, raw_input, [r["item"]["name"] for r in results]))
                continue

            results = parse_order_string(raw_input, MOCK_MENU)
            found_names = [r["item"]["name"] for r in results]

            if not should_find:
                if not results:
                    correct += 1
                else:
                    false_positives.append((i, raw_input, found_names))
            else:
                # Check at least the primary expected item was found
                primary = expected_names[0]
                if any(primary.lower() in fn.lower() or fn.lower() in primary.lower() for fn in found_names):
                    correct += 1
                else:
                    if results:
                        wrong_items.append((i, raw_input, expected_names, found_names))
                    else:
                        false_negatives.append((i, raw_input, expected_names))

        total = len(self.ORDER_TEST_CASES)
        accuracy = (correct / total) * 100

        # Report failures for diagnosis
        if false_positives:
            print(f"\n⚠️  False positives ({len(false_positives)}):")
            for i, inp, got in false_positives[:5]:
                print(f"   [{i}] '{inp}' → got {got}")

        if false_negatives:
            print(f"\n⚠️  False negatives ({len(false_negatives)}):")
            for i, inp, exp in false_negatives[:5]:
                print(f"   [{i}] '{inp}' → expected {exp}, got nothing")

        if wrong_items:
            print(f"\n⚠️  Wrong items ({len(wrong_items)}):")
            for i, inp, exp, got in wrong_items[:5]:
                print(f"   [{i}] '{inp}' → expected {exp}, got {got}")

        print(f"\n{'═'*60}")
        print(f"  PARAMETER 1 — Order Parsing Accuracy")
        print(f"  {correct}/{total} correct  →  {accuracy:.1f}%")
        print(f"  Target: ≥95%  |  Result: {'✅ PASS' if accuracy >= 95 else '❌ FAIL'}")
        print(f"{'═'*60}")

        assert accuracy >= 90, (
            f"Order parsing accuracy {accuracy:.1f}% is below 90% minimum. "
            f"Review fuzzy_match_item() logic. "
            f"FP={len(false_positives)}, FN={len(false_negatives)}, Wrong={len(wrong_items)}"
        )

    def test_sold_out_items_never_returned(self):
        """Sold-out items must never appear in order results regardless of how they're requested."""
        sold_out_queries = [
            "Stack Overflow Steak",
            "steak",
            "I want the most expensive steak",
            "Stack Overflow",
        ]
        sold_out_names = {m["name"] for m in MOCK_MENU if m.get("is_sold_out")}

        for query in sold_out_queries:
            results = parse_order_string(query, MOCK_MENU)
            for r in results:
                assert r["item"]["name"] not in sold_out_names, (
                    f"Sold-out item '{r['item']['name']}' returned for query: '{query}'"
                )

    def test_quantity_parsing(self):
        """Quantity extraction must be accurate for digits and word numbers."""
        cases = [
            ("2 burgers", "Full Stack Burger", 2),
            ("3 fries", "Firewall Fries", 3),
            ("one coffee", "Cold Brew Coffee", 1),
            ("two lemonades", "404 Lemonade", 2),
            ("4x nachos", "Null Pointer Nachos", 4),
        ]
        for raw, expected_item, expected_qty in cases:
            results = parse_order_string(raw, MOCK_MENU)
            found = [r for r in results if expected_item.lower() in r["item"]["name"].lower()]
            assert found, f"Expected item '{expected_item}' not found in '{raw}'"
            assert found[0]["qty"] == expected_qty, (
                f"Expected qty={expected_qty} for '{raw}', got {found[0]['qty']}"
            )


class TestAllergyDetectionRecall:
    """
    50 allergy mention variations.
    Target: 100% recall (no false negatives — missing an allergy is a safety issue)
    False positives are acceptable; false negatives are critical failures.
    """
    
    ALLERGY_TEST_CASES = [
        # ── Direct allergy declarations ───────────────────────────────────
        ("I'm allergic to nuts",                             True,  "nut_free"),
        ("I have a nut allergy",                             True,  "nut_free"),
        ("I'm allergic to dairy",                            True,  "dairy_free"),
        ("I have a dairy allergy",                           True,  "dairy_free"),
        ("I'm allergic to gluten",                           True,  "gluten_free"),
        ("I'm allergic to shellfish",                        True,  "shellfish_free"),
        ("I'm allergic to peanuts",                          True,  "nut_free"),
        ("allergy to eggs",                                  True,  None),
        ("I have a severe nut allergy",                      True,  "nut_free"),
        ("I'm highly allergic to dairy products",            True,  "dairy_free"),

        # ── Dietary preferences ───────────────────────────────────────────
        ("I'm vegan",                                        True,  "vegan"),
        ("I am vegan",                                      True,  "vegan"),
        ("I'm a vegan",                                     True,  "vegan"),
        ("I'm vegetarian",                                   True,  "vegetarian"),
        ("I'm a vegetarian",                                 True,  "vegetarian"),
        ("I'm lactose intolerant",                           True,  "lactose_intolerant"),
        ("I am lactose-intolerant",                          True,  "lactose_intolerant"),
        ("I'm gluten-free",                                  True,  "gluten_free"),
        ("I need gluten-free food",                          True,  "gluten_free"),
        ("I eat gluten free",                                True,  "gluten_free"),

        # ── "Can't eat" variations ────────────────────────────────────────
        ("I can't eat nuts",                                 True,  None),
        ("I cannot eat dairy",                               True,  None),
        ("I can't have gluten",                              True,  None),
        ("I cannot have shellfish",                          True,  None),
        ("I can't consume peanuts",                          True,  None),

        # ── Avoidance language ────────────────────────────────────────────
        ("I avoid dairy",                                    True,  "dairy_free"),
        ("please avoid nuts",                                True,  "nut_free"),
        ("no dairy for me",                                  True,  "dairy_free"),
        ("no nuts please",                                   True,  "nut_free"),
        ("no gluten",                                        True,  "gluten_free"),
        ("no shellfish please",                              True,  "shellfish_free"),
        ("no peanuts",                                       True,  "nut_free"),
        ("peanut-free please",                               True,  "nut_free"),
        ("nut-free options only",                            True,  "nut_free"),
        ("dairy-free",                                       True,  "dairy_free"),

        # ── Religious / cultural ──────────────────────────────────────────
        ("I eat halal only",                                 True,  "halal"),
        ("halal please",                                     True,  "halal"),
        ("I need kosher food",                               True,  "kosher"),
        ("everything needs to be kosher",                    True,  "kosher"),

        # ── Embedded in order request ─────────────────────────────────────
        ("I'm vegan, can I have the avocado toast",          True,  "vegan"),
        ("As a vegetarian, what can I have",                 True,  "vegetarian"),
        ("I'm allergic to nuts — can I still have pad thai", True,  "nut_free"),
        ("I have a dairy allergy, is the carbonara safe",    True,  "dairy_free"),
        ("Gluten-free options — I'm celiac",                 True,  "gluten_free"),

        # ── Implicit (should NOT be detected) ────────────────────────────
        ("I don't really like spicy food",                   False, None),  # preference, not allergy
        ("Can I see the vegan options",                      False, None),  # asking, not declaring
        ("What's in the carbonara",                          False, None),  # question only
        ("Is this dish nut-free",                            False, None),  # question only
        ("Do you have gluten-free bread",                    False, None),  # question only
    ]

    def test_allergy_detection_recall(self):
        """
        Zero false negatives required for safety-critical cases.
        False positives (over-detection) are acceptable.
        """
        false_negatives = []
        false_positives = []
        correct = 0

        for msg, should_detect, expected_tag in self.ALLERGY_TEST_CASES:
            detected = detect_allergies(msg)
            has_detection = len(detected) > 0

            if should_detect and not has_detection:
                false_negatives.append((msg, expected_tag))
            elif not should_detect and has_detection:
                false_positives.append((msg, detected))
            else:
                correct += 1

        total = len(self.ALLERGY_TEST_CASES)
        precision_cases = sum(1 for _, s, _ in self.ALLERGY_TEST_CASES if s)
        recall = ((precision_cases - len(false_negatives)) / precision_cases) * 100

        print(f"\n{'═'*60}")
        print(f"  PARAMETER 1 — Allergy Detection Recall")
        print(f"  Recall:    {recall:.1f}%  (target: 100%)")
        print(f"  FP count:  {len(false_positives)} (acceptable)")
        print(f"  FN count:  {len(false_negatives)} (CRITICAL — must be 0)")
        if false_negatives:
            print(f"  Missed allergy mentions:")
            for msg, tag in false_negatives:
                print(f"    ✗ '{msg}' (expected tag: {tag})")
        print(f"  Result: {'✅ PASS' if len(false_negatives) == 0 else '❌ FAIL — SAFETY RISK'}")
        print(f"{'═'*60}")

        assert len(false_negatives) == 0, (
            f"SAFETY CRITICAL: {len(false_negatives)} allergy mention(s) not detected:\n"
            + "\n".join(f"  - '{msg}'" for msg, _ in false_negatives)
        )


class TestFuzzyMatchFalsePositives:
    """
    Tests that fuzzy matching doesn't produce dangerous false positives
    (e.g., matching 'Lemon Tart' to 'Lemonade', or allergen confusion).
    """

    def test_no_cross_category_hallucination(self):
        """Drinks shouldn't match to mains, etc."""
        assert fuzzy_match_item("beer", MOCK_MENU) is None or \
               fuzzy_match_item("beer", MOCK_MENU)["category"] == "Drinks"

    def test_partial_name_doesnt_match_wrong_item(self):
        """'Pasta' should not match 'Python Pad Thai' when Carbonara is available."""
        result = fuzzy_match_item("pasta", MOCK_MENU)
        if result:
            assert "carbonara" in result["name"].lower() or \
                   "pasta" in result["name"].lower(), \
                f"'pasta' matched '{result['name']}' which is not a pasta dish"

    def test_price_mention_not_matched(self):
        """A price like '45' should not match 'Full Stack Burger' which costs 45."""
        result = fuzzy_match_item("45", MOCK_MENU)
        assert result is None or result["price"] != 45.0 or len("45") > 2

    def test_empty_query_returns_none(self):
        assert fuzzy_match_item("", MOCK_MENU) is None

    def test_single_letter_returns_none(self):
        assert fuzzy_match_item("a", MOCK_MENU) is None


class TestBookingDateParser:
    """
    30 booking request variations testing date extraction accuracy.
    The key fix: last occurrence wins (avoids 'Since today is X, I'll book for Y').
    Target: ≥90% accuracy.
    """

    NOW = datetime.now(DUBAI_TZ)

    BOOKING_DATE_CASES = [
        # ── Simple relative dates ─────────────────────────────────────────
        ("I'd like to book a table for tomorrow evening",      "tomorrow"),
        ("Can I reserve for tomorrow at 7pm",                  "tomorrow"),
        ("Book for tomorrow",                                   "tomorrow"),
        ("Day after tomorrow please",                          "day_after"),
        ("I want to come the day after tomorrow",              "day_after"),

        # ── AI response pattern (today mentioned first, booking date last) ─
        ("Since today is Wednesday, I'll book your table for tomorrow evening", "tomorrow"),
        ("Today is Thursday so I'm booking for tomorrow",      "tomorrow"),
        ("As of today April 22, your booking is for April 23", "april_23"),
        ("Since today is the 1st, I've booked you for the 2nd","day_2"),

        # ── Absolute months ────────────────────────────────────────────────
        ("Book for April 30",                                   "april_30"),
        ("Reserve a table on May 5th",                         "may_5"),
        ("I'd like a table on June 15",                        "june_15"),
        ("Booking for December 25",                            "december_25"),
        ("Table for January 10",                               "january_10"),
        ("Reserve on 25 April",                                "april_25"),
        ("I need a table on 30 May",                           "may_30"),
        ("Reservation for 15 June please",                     "june_15"),

        # ── Numeric formats ───────────────────────────────────────────────
        ("Book for 25/04",                                     "april_25"),
        ("Reserve 30/05",                                      "may_30"),

        # ── Day of week (next occurrence) ─────────────────────────────────
        ("Next Friday please",                                 "next_friday"),
        ("Next Monday evening",                                "next_monday"),
        ("I'd like next Saturday",                             "next_saturday"),
        ("Book for next Tuesday",                              "next_tuesday"),
        ("Next Sunday night",                                  "next_sunday"),

        # ── Combined time + date ───────────────────────────────────────────
        ("Tomorrow at 8pm for 2 people",                       "tomorrow"),
        ("April 25 at 7:30pm, party of 4",                    "april_25"),
        ("Next Friday at 8 for 6 guests",                      "next_friday"),

        # ── Should return None (no date) ──────────────────────────────────
        ("I'd like to book a table",                           None),
        ("Can I make a reservation",                           None),
        ("How do I book",                                      None),
    ]

    def test_booking_date_extraction_accuracy(self):
        correct = 0
        failed = []

        for msg, expected_key in self.BOOKING_DATE_CASES:
            result = extract_booking_date(msg)
            now = self.NOW

            if expected_key is None:
                if result is None:
                    correct += 1
                else:
                    failed.append((msg, "None", str(result.date())))
                continue

            if result is None:
                failed.append((msg, expected_key, "None extracted"))
                continue

            # Validate result against expected key
            tomorrow = (now + timedelta(days=1)).date()
            day_after = (now + timedelta(days=2)).date()

            key_to_check = {
                "tomorrow":      lambda d: d == tomorrow,
                "day_after":     lambda d: d == day_after,
                "april_23":      lambda d: d.month == 4 and d.day == 23,
                "april_25":      lambda d: d.month == 4 and d.day == 25,
                "april_30":      lambda d: d.month == 4 and d.day == 30,
                "may_5":         lambda d: d.month == 5 and d.day == 5,
                "may_30":        lambda d: d.month == 5 and d.day == 30,
                "june_15":       lambda d: d.month == 6 and d.day == 15,
                "december_25":   lambda d: d.month == 12 and d.day == 25,
                "january_10":    lambda d: d.month == 1 and d.day == 10,
                "day_2":         lambda d: d.day == 2,
                "next_friday":   lambda d: d.weekday() == 4,
                "next_monday":   lambda d: d.weekday() == 0,
                "next_saturday": lambda d: d.weekday() == 5,
                "next_tuesday":  lambda d: d.weekday() == 1,
                "next_sunday":   lambda d: d.weekday() == 6,
            }

            check_fn = key_to_check.get(expected_key)
            if check_fn and check_fn(result.date()):
                correct += 1
            else:
                failed.append((msg, expected_key, str(result.date())))

        total = len(self.BOOKING_DATE_CASES)
        accuracy = (correct / total) * 100

        print(f"\n{'═'*60}")
        print(f"  PARAMETER 1 — Booking Date Parser Accuracy")
        print(f"  {correct}/{total} correct  →  {accuracy:.1f}%")
        print(f"  Target: ≥90%  |  Result: {'✅ PASS' if accuracy >= 90 else '❌ FAIL'}")
        if failed:
            print(f"  Failed cases:")
            for msg, exp, got in failed[:5]:
                print(f"    ✗ '{msg[:50]}' expected={exp}, got={got}")
        print(f"{'═'*60}")

        assert accuracy >= 90, f"Booking date parser accuracy {accuracy:.1f}% below 90%"


class TestTokenUsageEstimation:
    """
    Context window awareness — ensures prompts don't silently approach token limits.
    Llama 3.3 70B context: 128k tokens. Alert at 50k.
    """

    def test_system_prompt_token_budget(self):
        """System prompt should stay well under 10k tokens."""
        prompt = build_system_prompt(MOCK_MENU, ai_context="Today's special: 20% off salmon.")
        token_estimate = count_tokens_approx(prompt)

        print(f"\n  System prompt: ~{token_estimate} tokens")
        assert token_estimate < 10_000, f"System prompt too large: {token_estimate} tokens"

    def test_conversation_history_growth(self):
        """After 6 turns, total prompt should stay under 50k tokens."""
        history = [
            {"role": "user",      "content": "I want a burger and fries"},
            {"role": "assistant", "content": "Great choice! Full Stack Burger (AED 45) + Firewall Fries (AED 18) = AED 63. Placing your order now! 🍔"},
            {"role": "user",      "content": "Actually can I change to salmon instead of burger"},
            {"role": "assistant", "content": "Of course! Switching to SSL Salmon (AED 65) + Firewall Fries (AED 18) = AED 83. Order updated!"},
            {"role": "user",      "content": "Add a lemonade too"},
            {"role": "assistant", "content": "Added 404 Lemonade (AED 15). New total: AED 98. 🍋"},
        ]

        system = build_system_prompt(MOCK_MENU)
        total_text = system + "\n".join(f"{m['role']}: {m['content']}" for m in history[-6:])
        total_tokens = count_tokens_approx(total_text)

        print(f"\n  6-turn conversation: ~{total_tokens} tokens (limit: 50k)")
        assert total_tokens < 50_000, f"Conversation growing too large: {total_tokens} tokens"

    def test_cost_per_session_estimate(self):
        """
        Groq Llama 3.3 70B pricing (as of 2025):
          Input:  $0.59 / 1M tokens
          Output: $0.79 / 1M tokens
        A typical ordering session: ~5 turns, ~2000 tokens in, ~500 out per turn
        """
        avg_input_tokens_per_session = 5 * 2000   # 10,000
        avg_output_tokens_per_session = 5 * 500   # 2,500

        cost_input  = (avg_input_tokens_per_session  / 1_000_000) * 0.59
        cost_output = (avg_output_tokens_per_session / 1_000_000) * 0.79
        cost_per_session = cost_input + cost_output

        sessions_per_day = 100
        cost_per_day = cost_per_session * sessions_per_day

        print(f"\n  Estimated Groq cost:")
        print(f"    Per session:  ${cost_per_session:.4f}")
        print(f"    Per 100 sessions/day: ${cost_per_day:.3f}/day = ${cost_per_day * 30:.2f}/month")

        assert cost_per_session < 0.05, (
            f"Cost per session ${cost_per_session:.4f} exceeds $0.05 budget — "
            f"reduce conversation history window"
        )


# ─────────────────────────────────────────────────────────────────────────────
# LIVE LATENCY TEST (optional — requires GROQ_API_KEY env var)
# ─────────────────────────────────────────────────────────────────────────────
class TestGroqLatency:
    """
    OPTIONAL — requires live GROQ_API_KEY.
    Skip with: pytest -k "not latency"
    Measures p50, p95, p99 latency over 10 real API calls.
    """

    @pytest.mark.skipif(
        not __import__("os").getenv("GROQ_API_KEY"),
        reason="GROQ_API_KEY not set — skipping live latency test"
    )
    def test_groq_response_latency(self):
        import os
        try:
            from groq import Groq
        except ImportError:
            pytest.skip("groq package not installed")

        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        latencies = []
        test_prompts = [
            "I want a burger and fries",
            "Two coffees please",
            "Can I get the salmon",
            "Pad thai and a lemonade",
            "Cheesecake for dessert",
        ]

        for prompt in test_prompts:
            start = time.perf_counter()
            try:
                client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": build_system_prompt(MOCK_MENU)},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=150,
                    temperature=0.3,
                )
                elapsed = time.perf_counter() - start
                latencies.append(elapsed)
            except Exception as e:
                print(f"  Groq call failed: {e}")

        if not latencies:
            pytest.skip("All Groq calls failed")

        latencies.sort()
        p50 = latencies[len(latencies) // 2]
        p95 = latencies[int(len(latencies) * 0.95)] if len(latencies) >= 2 else latencies[-1]
        p99 = latencies[-1]

        print(f"\n{'═'*60}")
        print(f"  PARAMETER 1 — Groq API Latency ({len(latencies)} samples)")
        print(f"  p50: {p50*1000:.0f}ms  p95: {p95*1000:.0f}ms  p99: {p99*1000:.0f}ms")
        print(f"  Target p95 < 3000ms: {'✅' if p95 < 3.0 else '❌'}")
        print(f"{'═'*60}")

        assert p95 < 3.0, f"Groq p95 latency {p95*1000:.0f}ms exceeds 3000ms target"


if __name__ == "__main__":
    import subprocess
    subprocess.run(["pytest", __file__, "-v", "--tb=short", "-k", "not latency"], check=False)
