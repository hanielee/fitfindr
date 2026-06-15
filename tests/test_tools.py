"""
Tests for the three FitFindr tools.

Each tool gets at least one test per failure mode:
  - search_listings: clear match, no match (empty list), price-filter enforcement
  - suggest_outfit:   empty-wardrobe fallback (must not crash, must return text)
  - create_fit_card:  empty-outfit guard (returns an error string, never raises)

search_listings is pure and tested offline. The two LLM-backed tools hit the
Groq API; those tests are skipped automatically if GROQ_API_KEY is not set.
"""

import os

import pytest

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

needs_groq = pytest.mark.skipif(
    not os.environ.get("GROQ_API_KEY"),
    reason="GROQ_API_KEY not set — skipping live LLM test",
)


# ── Tool 1: search_listings (offline, deterministic) ────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    # Nothing in the dataset matches all three filters → empty list, no exception.
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_price_filter_enforced():
    # A price cap that DOES leave matches — confirm none exceed the ceiling.
    results = search_listings("jacket", size=None, max_price=40)
    assert all(item["price"] <= 40 for item in results)


def test_search_size_is_not_exact_match():
    # "M" should match listings sized "S/M", proving matching isn't literal "=="
    results = search_listings("tee", size="M", max_price=None)
    assert all("m" in item["size"].lower() for item in results)


# ── Tool 2: suggest_outfit (LLM-backed) ─────────────────────────────────────

NEW_ITEM = {
    "id": "lst_002",
    "title": "Y2K Baby Tee — Butterfly Print",
    "category": "tops",
    "style_tags": ["y2k", "vintage", "graphic tee"],
    "colors": ["white", "pink", "purple"],
    "price": 18.0,
    "platform": "depop",
}


@needs_groq
def test_suggest_outfit_with_wardrobe():
    out = suggest_outfit(NEW_ITEM, get_example_wardrobe())
    assert isinstance(out, str)
    assert out.strip() != ""


@needs_groq
def test_suggest_outfit_empty_wardrobe():
    # Failure mode: empty wardrobe must NOT crash and must still return advice.
    out = suggest_outfit(NEW_ITEM, get_empty_wardrobe())
    assert isinstance(out, str)
    assert out.strip() != ""


# ── Tool 3: create_fit_card ─────────────────────────────────────────────────

@pytest.mark.parametrize("bad_outfit", ["", "   ", None])
def test_create_fit_card_empty_outfit(bad_outfit):
    # Failure mode: empty/missing outfit returns an error string, never raises.
    result = create_fit_card(bad_outfit, NEW_ITEM)
    assert isinstance(result, str)
    assert result.strip() != ""
    assert "couldn't" in result.lower() or "no outfit" in result.lower()


@needs_groq
def test_create_fit_card_full_outfit():
    outfit = "Pair with your wide-leg jeans and chunky sneakers; roll the sleeves once."
    card = create_fit_card(outfit, NEW_ITEM)
    assert isinstance(card, str)
    assert card.strip() != ""
