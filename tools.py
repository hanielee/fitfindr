"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

# Model used by the two LLM-backed tools.
_MODEL = "llama-3.3-70b-versatile"


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()
    results = []

    # Query terms used for relevance scoring (lowercased, deduped).
    query_terms = [t for t in re.findall(r"[a-z0-9]+", description.lower())]

    for item in listings:
        # 1. Hard price filter (done in code, not by the LLM).
        if max_price is not None and item["price"] > max_price:
            continue

        # 2. Size filter — token-based and case-insensitive so "M" matches
        #    "S/M" without "S" wrongly matching "One Size".
        if size is not None and not _size_matches(size, item["size"]):
            continue

        # 3. Score by keyword overlap across the searchable text fields.
        searchable = " ".join(
            str(field).lower()
            for field in (
                item["title"],
                item["description"],
                item["category"],
                item.get("brand") or "",
                " ".join(item.get("style_tags", [])),
            )
        )
        score = sum(1 for term in set(query_terms) if term in searchable)

        # 4. Drop anything with no keyword match at all.
        if score == 0:
            continue

        results.append((score, item))

    # 5. Sort by score (best first); break ties by lower price for determinism.
    results.sort(key=lambda pair: (-pair[0], pair[1]["price"]))
    return [item for _, item in results]


def _size_matches(requested: str, listing_size: str) -> bool:
    """True if `requested` matches a size token in `listing_size`.

    Splits the listing's size string on separators ("S/M", "W30 L30",
    "XL (oversized)") into tokens and compares each token case-insensitively
    to the requested size. Token comparison avoids substring false positives
    (e.g. "S" matching the "s" in "One Size").
    """
    wanted = requested.strip().lower()
    if not wanted:
        return True
    tokens = re.split(r"[\s/()]+", listing_size.lower())
    return wanted in {t for t in tokens if t}


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    client = _get_groq_client()

    item_desc = (
        f"{new_item.get('title', 'this item')} "
        f"({new_item.get('category', 'unknown category')}, "
        f"colors: {', '.join(new_item.get('colors', [])) or 'n/a'}, "
        f"style: {', '.join(new_item.get('style_tags', [])) or 'n/a'})"
    )

    items = wardrobe.get("items", [])

    if not items:
        # Empty-wardrobe case is expected, not an error: give standalone advice.
        prompt = (
            f"A user is considering buying this thrifted item:\n  {item_desc}\n\n"
            "They have not logged any wardrobe items yet, so you cannot reference "
            "specific pieces they own. Give general styling advice for this item: "
            "what kinds of pieces pair well with it, what vibe it suits, and one or "
            "two concrete outfit ideas built around common staples. Keep it to "
            "3-4 sentences, friendly and specific."
        )
    else:
        wardrobe_lines = "\n".join(
            f"  - {it.get('name', it.get('id', 'item'))} "
            f"({it.get('category', '?')}, "
            f"colors: {', '.join(it.get('colors', [])) or 'n/a'}, "
            f"style: {', '.join(it.get('style_tags', [])) or 'n/a'})"
            for it in items
        )
        prompt = (
            f"A user is considering buying this thrifted item:\n  {item_desc}\n\n"
            f"Here is everything currently in their wardrobe:\n{wardrobe_lines}\n\n"
            "Suggest 1-2 complete outfits that pair the new item with specific "
            "pieces from their wardrobe above. Only reference pieces that actually "
            "appear in the list — do not invent items they do not own. Name the "
            "pieces explicitly and add a concrete styling tip (how to wear it). "
            "Keep it to 3-4 sentences, friendly and specific."
        )

    response = client.chat.completions.create(
        model=_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a thrift-savvy personal stylist. You give concrete, "
                    "wearable outfit advice in a warm, casual voice."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
    )
    return response.choices[0].message.content.strip()


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    # 1. Guard against an empty / whitespace-only / missing outfit string.
    if not outfit or not outfit.strip():
        return (
            "Couldn't write a fit card: no outfit suggestion was provided. "
            "Run suggest_outfit first to generate styling text."
        )

    client = _get_groq_client()

    title = new_item.get("title", "this piece")
    price = new_item.get("price")
    platform = new_item.get("platform", "online")
    price_str = f"${price:g}" if isinstance(price, (int, float)) else "a steal"

    prompt = (
        f"Write a short, shareable social-media caption for a thrifted find.\n\n"
        f"Item: {title}\n"
        f"Price: {price_str}\n"
        f"Platform: {platform}\n"
        f"Outfit / styling notes: {outfit}\n\n"
        "Write 2-4 sentences that feel like a real OOTD post (not a product "
        "description). Mention the item name, the price, and the platform "
        "naturally — once each. Capture the outfit vibe in specific terms. "
        "Casual, authentic, a little playful. An emoji or two is fine."
    )

    response = client.chat.completions.create(
        model=_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You write punchy, authentic thrift-flip captions for "
                    "Instagram and TikTok."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        # Higher temperature so repeated calls on the same input vary.
        temperature=1.0,
    )
    return response.choices[0].message.content.strip()
