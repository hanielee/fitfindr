"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
        # --- bookkeeping the loop uses for branching / explanatory notes ---
        "retry_count": 0,            # how many times search was loosened
        "loosened": [],             # human-readable record of what was loosened
        "wardrobe_empty": False,     # True if suggest_outfit got an empty closet
    }


# ── query parsing ─────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Pull a search `description`, optional `size`, and optional `max_price` out of
    a natural-language query using regex (no LLM call — parsing is cheap and
    deterministic, documented as the regex choice in planning.md).

    "vintage graphic tee under $30, size M"
        → {"description": "vintage graphic tee", "size": "M", "max_price": 30.0}
    """
    text = query.strip()

    # max_price: "under $30", "below 30", "$30", "under 30 dollars"
    max_price = None
    price_match = re.search(
        r"(?:under|below|less than|max|<)?\s*\$?\s*(\d+(?:\.\d+)?)\s*(?:dollars|usd|\$)?",
        text,
        flags=re.IGNORECASE,
    )
    # Only treat a number as a price if it's tied to a price cue ($, "under", etc.)
    price_cue = re.search(
        r"(?:under|below|less than|max|\$)\s*\$?\s*(\d+(?:\.\d+)?)",
        text,
        flags=re.IGNORECASE,
    )
    if price_cue:
        max_price = float(price_cue.group(1))

    # size: "size M", "size XXS", "in size 8"
    size = None
    size_match = re.search(r"\bsize\s+([A-Za-z0-9/]+)", text, flags=re.IGNORECASE)
    if size_match:
        size = size_match.group(1)

    # description: strip the price clause, size clause, and common filler words.
    description = text
    description = re.sub(
        r"(?:under|below|less than|max)\s*\$?\s*\d+(?:\.\d+)?\s*(?:dollars|usd)?",
        "",
        description,
        flags=re.IGNORECASE,
    )
    description = re.sub(r"\$\s*\d+(?:\.\d+)?", "", description)
    description = re.sub(r"\bsize\s+[A-Za-z0-9/]+", "", description, flags=re.IGNORECASE)
    description = re.sub(
        r"\b(?:i'?m|looking|for|a|an|the|some|find|me|please|what'?s|out|there|in)\b",
        "",
        description,
        flags=re.IGNORECASE,
    )
    description = re.sub(r"[,.]", " ", description)
    description = re.sub(r"\s+", " ", description).strip()
    if not description:
        description = text  # fall back to the raw query if we stripped everything

    return {"description": description, "size": size, "max_price": max_price}


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.

    TODO — implement this function using the planning loop you designed in planning.md:

        Step 1: Initialize the session with _new_session().

        Step 2: Parse the user's query to extract a description, size, and
                max_price. You can use regex, string splitting, or ask the LLM
                to parse it — document your choice in planning.md.
                Store the result in session["parsed"].

        Step 3: Call search_listings() with the parsed parameters.
                Store results in session["search_results"].
                If no results: set session["error"] to a helpful message and
                return the session early. Do NOT proceed to suggest_outfit
                with empty input.

        Step 4: Select the item to use (e.g., the top result).
                Store it in session["selected_item"].

        Step 5: Call suggest_outfit() with the selected item and wardrobe.
                Store the result in session["outfit_suggestion"].

        Step 6: Call create_fit_card() with the outfit suggestion and selected item.
                Store the result in session["fit_card"].

        Step 7: Return the session.

    Before writing code, complete the Planning Loop and State Management sections
    of planning.md — your implementation should match what you described there.
    """
    # Step 1 — build the single session object once; everything flows through it.
    session = _new_session(query, wardrobe)

    # Step 2 — parse the query into search parameters and record them in state.
    session["parsed"] = _parse_query(query)
    description = session["parsed"]["description"]
    size = session["parsed"]["size"]
    max_price = session["parsed"]["max_price"]

    # Step 3 — SEARCH, with up to two constraint-loosening retries (per planning.md).
    #          The loop BRANCHES on what search returns: empty vs. non-empty.
    while True:
        results = search_listings(description, size=size, max_price=max_price)
        if results:
            break  # found matches — stop loosening and move on

        if session["retry_count"] >= 2:
            break  # exhausted retries — will fall through to the error branch

        # Loosen exactly one constraint per retry.
        if session["retry_count"] == 0 and max_price is not None:
            max_price = round(max_price * 1.5, 2)
            session["loosened"].append(f"raised your price cap to ${max_price:g}")
        elif size is not None:
            size = None  # treat size as a soft preference rather than a hard filter
            session["loosened"].append("relaxed the size filter")
        else:
            # Nothing left to loosen (no price/size given) — don't spin retries.
            session["retry_count"] = 2
            continue
        session["retry_count"] += 1

    session["search_results"] = results

    # Branch A — NO matches: set a helpful error and STOP. Do not call the other
    # two tools. This is the conditional that makes the agent behave differently.
    if not results:
        tried = ""
        if session["loosened"]:
            tried = " I also tried " + ", then ".join(session["loosened"]) + "."
        session["error"] = (
            f"No listings matched “{description}”"
            + (f" in size {session['parsed']['size']}" if session["parsed"]["size"] else "")
            + (f" under ${session['parsed']['max_price']:g}" if session["parsed"]["max_price"] else "")
            + f".{tried} Try raising your price, dropping the size filter, or "
            "describing the item differently (e.g. a broader category or style)."
        )
        return session  # early return — fit_card and outfit_suggestion stay None

    # Step 4 — Branch B: pick the top-ranked match and carry it in the session.
    session["selected_item"] = results[0]

    # Step 5 — suggest an outfit. suggest_outfit handles an empty wardrobe itself
    #          (general styling advice), so we pass the SAME selected_item dict
    #          straight through — no re-prompting, no hardcoded values.
    session["wardrobe_empty"] = not wardrobe.get("items")
    session["outfit_suggestion"] = suggest_outfit(session["selected_item"], wardrobe)

    # Step 6 — turn the outfit + item into a shareable caption. The exact string
    #          returned by suggest_outfit is what goes in; nothing is re-fetched.
    session["fit_card"] = create_fit_card(
        session["outfit_suggestion"], session["selected_item"]
    )

    # Step 7 — done. Caller checks session["error"] (None here) then reads outputs.
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
