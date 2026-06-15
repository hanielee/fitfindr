"""
app.py

Gradio interface for FitFindr — styled like a Depop storefront.

Run with:
    python app.py

Then open the localhost URL shown in your terminal (usually http://localhost:7860,
but check your terminal — the port may differ).
"""

import html

import gradio as gr

from agent import run_agent
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── presentation helpers ──────────────────────────────────────────────────────

CATEGORY_EMOJI = {
    "tops": "👕",
    "bottoms": "👖",
    "outerwear": "🧥",
    "shoes": "👟",
    "accessories": "👜",
}


def _esc(text) -> str:
    """Escape text so LLM / listing output can't break the card markup."""
    return html.escape(str(text)) if text is not None else ""


def _listing_card(item: dict) -> str:
    """Render the top listing as a Depop-style product card."""
    emoji = CATEGORY_EMOJI.get(item.get("category", ""), "🛍️")
    brand = item.get("brand")
    seller = _esc(brand) if brand else "secondhand seller"
    tags = "".join(
        f'<span class="dp-tag">{_esc(t)}</span>'
        for t in item.get("style_tags", [])[:4]
    )
    return f"""
<div class="dp-card dp-listing">
  <div class="dp-thumb">
    <span class="dp-emoji">{emoji}</span>
    <span class="dp-price">${item['price']:g}</span>
  </div>
  <div class="dp-listing-body">
    <h3 class="dp-title">{_esc(item['title'])}</h3>
    <div class="dp-meta">
      <span class="dp-platform">@{_esc(item['platform'])}</span>
      <span class="dp-dot">·</span>
      <span>{_esc(item['condition'])}</span>
      <span class="dp-dot">·</span>
      <span>Size {_esc(item['size'])}</span>
    </div>
    <p class="dp-desc">{_esc(item['description'])}</p>
    <div class="dp-tags">{tags}</div>
    <div class="dp-seller">Listed by {seller}</div>
  </div>
</div>
""".strip()


def _text_card(kind_class: str, heading: str, body: str) -> str:
    """Render the outfit idea / fit card as a soft content card."""
    return f"""
<div class="dp-card {kind_class}">
  <div class="dp-card-head">{heading}</div>
  <p class="dp-card-text">{_esc(body)}</p>
</div>
""".strip()


def _error_card(message: str) -> str:
    return f"""
<div class="dp-card dp-error">
  <div class="dp-card-head">😕 Nothing matched</div>
  <p class="dp-card-text">{_esc(message)}</p>
</div>
""".strip()


def _empty_card(label: str) -> str:
    return f'<div class="dp-card dp-empty">{_esc(label)}</div>'


# ── query handler ─────────────────────────────────────────────────────────────

def handle_query(user_query: str, wardrobe_choice: str) -> tuple[str, str, str]:
    """
    Called by Gradio when the user submits a query.

    Returns a tuple of three HTML strings, one per output panel:
        (listing_card, outfit_card, fit_card)
    """
    # 1. Guard against an empty query.
    if not user_query or not user_query.strip():
        return (
            _error_card("Type what you're hunting for first — e.g. "
                        "“vintage graphic tee under $30”."),
            "",
            "",
        )

    # 2. Select the wardrobe based on the radio choice.
    if wardrobe_choice == "Empty wardrobe (new user)":
        wardrobe = get_empty_wardrobe()
    else:
        wardrobe = get_example_wardrobe()

    # 3. Run the planning loop.
    session = run_agent(user_query, wardrobe)

    # 4. Error / no-results branch — surface the message, leave the rest blank.
    if session["error"]:
        return _error_card(session["error"]), "", ""

    # 5. Map the session into three styled cards.
    listing_html = _listing_card(session["selected_item"])
    outfit_html = _text_card("dp-outfit", "👗 How to style it", session["outfit_suggestion"])
    fitcard_html = _text_card("dp-fit", "✨ Ready-to-post caption", session["fit_card"])
    return listing_html, outfit_html, fitcard_html


# ── styling ───────────────────────────────────────────────────────────────────

DEPOP_RED = "#FF2300"

CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@500;700&display=swap');

:root { --dp-red: #FF2300; }

.gradio-container {
    max-width: 1080px !important;
    margin: 0 auto !important;
    background: #ffffff !important;
    font-family: 'Inter', system-ui, sans-serif !important;
}
.gradio-container * { font-family: 'Inter', system-ui, sans-serif; }

/* hide default gradio footer */
footer { display: none !important; }

/* ── header / wordmark ─────────────────────────────────────────── */
#dp-header {
    text-align: center;
    padding: 28px 0 6px 0;
    border-bottom: 1px solid #ececec;
    margin-bottom: 22px;
}
#dp-header .dp-wordmark {
    font-family: 'Space Grotesk', sans-serif;
    font-weight: 700;
    font-size: 40px;
    letter-spacing: -1.5px;
    color: #000;
}
#dp-header .dp-wordmark .dot { color: var(--dp-red); }
#dp-header .dp-sub {
    color: #767676;
    font-size: 15px;
    margin-top: 2px;
}

/* ── search bar ────────────────────────────────────────────────── */
#dp-search textarea, #dp-search input {
    border-radius: 999px !important;
    border: 1.5px solid #000 !important;
    padding: 14px 20px !important;
    font-size: 16px !important;
    box-shadow: none !important;
    background: #fff !important;
}
#dp-search textarea:focus, #dp-search input:focus {
    border-color: var(--dp-red) !important;
}
#dp-search label span, #dp-wardrobe label span, #dp-wardrobe legend {
    font-weight: 600 !important;
    color: #000 !important;
}

/* radio chips */
#dp-wardrobe .wrap label {
    border-radius: 999px !important;
    border: 1.5px solid #d9d9d9 !important;
    padding: 8px 14px !important;
    margin: 4px 6px 4px 0 !important;
}
#dp-wardrobe input:checked + span,
#dp-wardrobe .selected { color: #000 !important; }

/* ── primary button ────────────────────────────────────────────── */
button.primary, #dp-submit button, #dp-submit.primary {
    background: #000 !important;
    color: #fff !important;
    border: none !important;
    border-radius: 999px !important;
    font-weight: 700 !important;
    font-size: 16px !important;
    letter-spacing: 0.2px;
    padding: 14px 0 !important;
    transition: background 0.15s ease;
}
button.primary:hover, #dp-submit button:hover {
    background: var(--dp-red) !important;
}

/* ── cards ─────────────────────────────────────────────────────── */
.dp-card {
    border: 1px solid #ececec;
    border-radius: 16px;
    background: #fff;
    overflow: hidden;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.dp-empty {
    color: #b3b3b3;
    text-align: center;
    padding: 40px 18px;
    font-size: 14px;
    border-style: dashed;
}

/* listing card */
.dp-thumb {
    position: relative;
    background: #f6f6f6;
    height: 190px;
    display: flex;
    align-items: center;
    justify-content: center;
}
.dp-emoji { font-size: 76px; line-height: 1; }
.dp-price {
    position: absolute;
    bottom: 12px;
    right: 12px;
    background: #000;
    color: #fff;
    font-weight: 700;
    font-size: 15px;
    padding: 5px 12px;
    border-radius: 999px;
}
.dp-listing-body { padding: 16px 18px 18px; }
.dp-title {
    font-family: 'Space Grotesk', sans-serif;
    font-weight: 700;
    font-size: 18px;
    margin: 0 0 6px 0;
    color: #000;
}
.dp-meta { color: #767676; font-size: 13px; margin-bottom: 10px; }
.dp-dot { margin: 0 6px; }
.dp-platform { color: var(--dp-red); font-weight: 600; }
.dp-desc { color: #333; font-size: 14px; line-height: 1.5; margin: 0 0 12px; }
.dp-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.dp-tag {
    background: #f2f2f2;
    color: #444;
    font-size: 12px;
    padding: 4px 10px;
    border-radius: 999px;
}
.dp-seller {
    border-top: 1px solid #f0f0f0;
    padding-top: 10px;
    color: #999;
    font-size: 12px;
}

/* text cards */
.dp-card-head {
    font-family: 'Space Grotesk', sans-serif;
    font-weight: 700;
    font-size: 16px;
    padding: 14px 18px;
    border-bottom: 1px solid #f0f0f0;
    color: #000;
}
.dp-card-text { padding: 16px 18px; font-size: 14.5px; line-height: 1.6; color: #222; margin: 0; }
.dp-fit .dp-card-text { font-style: italic; color: #111; }
.dp-error { border-color: #ffd6cf; background: #fff7f5; }
.dp-error .dp-card-head { color: var(--dp-red); border-bottom-color: #ffd6cf; }

.dp-section-label {
    font-family: 'Space Grotesk', sans-serif;
    font-weight: 600;
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #999;
    margin: 8px 0 -6px 2px;
}
"""


# ── interface ─────────────────────────────────────────────────────────────────

EXAMPLE_QUERIES = [
    "vintage graphic tee under $30",
    "90s track jacket in size M",
    "flowy midi skirt under $40",
    "black combat boots size 8",
    "designer ballgown size XXS under $5",   # deliberate no-results test
]


def build_interface():
    theme = gr.themes.Base(
        font=[gr.themes.GoogleFont("Inter"), "system-ui", "sans-serif"],
        primary_hue=gr.themes.colors.red,
        neutral_hue=gr.themes.colors.gray,
    )

    with gr.Blocks(title="FitFindr", theme=theme, css=CUSTOM_CSS) as demo:
        gr.HTML(
            """
            <div id="dp-header">
              <div class="dp-wordmark">fitfindr<span class="dot">.</span></div>
              <div class="dp-sub">find secondhand pieces &amp; get outfit ideas from your wardrobe</div>
            </div>
            """
        )

        with gr.Row():
            query_input = gr.Textbox(
                label="Search",
                placeholder="e.g. vintage graphic tee under $30, size M",
                lines=1,
                elem_id="dp-search",
                scale=3,
            )
            wardrobe_choice = gr.Radio(
                choices=["Example wardrobe", "Empty wardrobe (new user)"],
                value="Example wardrobe",
                label="Your closet",
                elem_id="dp-wardrobe",
                scale=1,
            )

        submit_btn = gr.Button("Find it", variant="primary", elem_id="dp-submit")

        gr.HTML('<div class="dp-section-label">Your results</div>')
        with gr.Row(equal_height=False):
            listing_output = gr.HTML(_empty_card("Your top match shows up here"))
            outfit_output = gr.HTML(_empty_card("Styling ideas show up here"))
            fitcard_output = gr.HTML(_empty_card("Your shareable caption shows up here"))

        gr.Examples(
            examples=[[q, "Example wardrobe"] for q in EXAMPLE_QUERIES],
            inputs=[query_input, wardrobe_choice],
            label="Trending searches",
        )

        outputs = [listing_output, outfit_output, fitcard_output]
        submit_btn.click(fn=handle_query, inputs=[query_input, wardrobe_choice], outputs=outputs)
        query_input.submit(fn=handle_query, inputs=[query_input, wardrobe_choice], outputs=outputs)

    return demo


if __name__ == "__main__":
    demo = build_interface()
    demo.launch()
