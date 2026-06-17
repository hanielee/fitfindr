# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
Filters the static 40-item listings dataset (loaded via load_listings() from data/listings.json) by keyword, size, and price ceiling, then ranks by how many query terms matched.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `description` (str): keyword text matched against the title, description, style_tags, category, and brand fields of each listing
- `size` (str): size of item, matched against size field
- `max_price` (float): upper-bound price of item in USD ($)

**What it returns:**
<!-- Describe the return value — what fields does a result contain? -->
A list of listing dicts pulled straight from the dataset, sorted by match relevance (how many query terms hit). Each dict carries the full record: id, title, description, category, style_tags, size, condition, price, colors, brand, platform. Example: {"id": "lst_0042", "title": "Faded Band Tee", "price": 22.0, "size": "M", "condition": "Good", "platform": "Depop", ...}.

**What happens if it fails or returns nothing:**
<!-- What should the agent do if no listings match? -->
If load_listings() throws (file missing or malformed JSON), the agent reports the catalog is unreachable and stops, since this isn't a network issue it can retry around. If the call succeeds but returns an empty list, that means nothing in the current dataset matches all three filters, not that a search "failed." The agent loosens one constraint at a time (raise max_price, drop size, broaden description) and re-queries, or tells the user no items match if loosening still comes up empty.

---

### Tool 2: suggest_outfit

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
Matches a new item against existing wardrobe items by category, color, and style tags, and writes a pairing recommendation with wear instructions.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `new_item` (dict): a listing-shaped record (same fields as a search_listings result: title, category, colors, style_tags, brand, etc.) representing the piece being added
- `wardrobe` (dict): the user's closet, structured per wardrobe_schema.json, sourced from get_example_wardrobe() (demo data) or get_empty_wardrobe() (new user, no items yet); items are presumably grouped by category with fields mirroring the listings shape (flagging this as inferred until I see the actual schema file)

**What it returns:**
<!-- Describe the return value -->
A string combining a specific pairing from the wardrobe with concrete styling instructions, e.g. "Pair this with your wide-leg jeans and platform Docs for a classic 90s grunge look. Roll the sleeves once and tuck the front corner slightly for shape."

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the wardrobe is empty or no outfit can be suggested? -->
If wardrobe came from get_empty_wardrobe(), there's nothing to pair against, so the tool returns no match. The agent should check for this case directly (empty wardrobe is an expected state, not an error) and either generate a standalone styling note for the new item alone, flagged as wardrobe-independent, or prompt the user to log a few wardrobe items first. If the wardrobe has items but none share a category or color the new item pairs with, same fallback applies. If the tool call errors outright, the agent skips this step and passes new_item directly to create_fit_card with no outfit text.

---

### Tool 3: create_fit_card

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
Converts the item details and outfit suggestion into a casual, thrift-flip-style caption (price, platform, emoji, sign-off).

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `outfit` (str | None): the styling text from suggest_outfit, or None if that step produced nothing
- `new_item` (dict): listing fields used to ground the caption, primarily title, price, platform, condition

**What it returns:**
<!-- Describe the return value -->
A finished caption string. Example: "thrifted this faded band tee off depop for $22 and honestly it was made for my wide-legs 🖤 full look in my stories"

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the outfit data is incomplete? -->
If outfit is None, the agent writes a stripped caption from new_item fields alone (name, price, platform) with no styling language, and tells the user the pairing line was left out. If create_fit_card itself errors, the agent falls back to showing the raw listing dict and any outfit text as plain text instead of a formatted caption.

---

### Additional Tools (if any)

<!-- Copy the block above for any tools beyond the required three -->

---

## Planning Loop

**How does your agent decide which tool to call next?**
<!-- Describe the logic your planning loop uses. What does it look at? What conditions change its behavior? How does it know when it's done? -->
The loop runs a fixed three-step pipeline rather than a free choice among tools, with decisions limited to skip, retry, or fallback branches inside each step. In step one it calls search_listings, drops any returned ID that doesn't exist in the canonical load_listings() output, and checks the remaining list length; if empty and retry_count is under 2 it loosens a constraint and retries, first by raising max_price 50%, then by telling the model to treat size as a soft preference rather than a hard requirement, incrementing retry_count each time; if still empty after two retries it sets an error_message and returns immediately without calling the other two tools; if results come back non-empty at any point it sets selected_item to results[0] and moves on. In step two it first checks wardrobe["items"]; if that list is empty it skips suggest_outfit entirely, sets outfit to None and wardrobe_empty to True, and goes straight to step three, since there's nothing to pair against and no reason to spend a call on it; if the wardrobe has items it calls suggest_outfit, catches any exception by setting outfit to None and styling_failed to True, and otherwise validates the response by confirming any wardrobe item it names actually exists in wardrobe["items"], retrying once with a stricter prompt if it hallucinated an item and falling back to outfit equals None if the retry also fails validation. In step three it calls create_fit_card with whatever outfit and selected_item ended up being; if outfit is None that's expected rather than an error, so create_fit_card produces a stripped caption and the loop appends a short note explaining why the styling line is missing; if create_fit_card itself raises an exception it sets degraded_output to True and returns the raw selected_item fields plus any outfit text instead of a formatted caption; otherwise it sets final_caption to the result. The run always ends in one of three states, a returned final_caption, a returned error_message from step one, or a returned degraded_output from step three, and nothing loops back to an earlier step; retries are local to their own step, two loosenings in step one and one regeneration in step two, and once those are exhausted the step either advances with a fallback value or the whole run terminates.

---

## State Management

**How does information from one tool get passed to the next?**
<!-- Describe how your agent stores and accesses state within a session. What data is tracked? How is it passed between tool calls? -->
A single session object gets created once at the top of the planning loop, before any tool call runs, and it's passed by reference through all three steps rather than recreated or merged at each stage. It's a plain dict with fixed keys: the original inputs (`description`, `size`, `max_price`, `wardrobe`), a `retry_count`, and then the fields each step writes as it completes (`selected_item`, `outfit`, `wardrobe_empty`, `styling_failed`, `degraded_output`, `final_caption`, `error_message`). Nothing gets serialized or written to a database between calls. It's an in-memory object that lives for the duration of one request and gets discarded once the loop returns.

The tools themselves never touch this object. `search_listings`, `suggest_outfit`, and `create_fit_card` are plain functions that take explicit arguments and return a value, with no awareness that a session even exists. The loop is the only thing that reads from and writes to it, which keeps each tool testable on its own with a direct function call and a fixed input, no mock session required.

The actual handoff works like this. After `search_listings` returns and its IDs get validated against `load_listings()`, the loop does `session["selected_item"] = results[0]`. When it calls `suggest_outfit`, it passes `session["selected_item"]` as the `new_item` argument directly, not anything re-typed or re-fetched from the user. Same pattern on the next handoff: `suggest_outfit`'s return value gets written to `session["outfit"]`, and that's the literal value passed as the `outfit` argument into `create_fit_card`. So the "passing" is really just the loop reading a value out of one tool's return, writing it into a named session key, and handing that same session key to the next tool's parameter, with no transformation in between.

The flag fields (`wardrobe_empty`, `styling_failed`, `degraded_output`) work the same way but feed the loop's own branching rather than a tool's input. They're set by the loop after inspecting a tool's output or catching an exception, and they're read back by the loop later, both to decide whether to append an explanatory note to the final response and to determine which of the three terminal states (`final_caption`, `error_message`, `degraded_output`) gets returned at the end.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Loosens one constraint and retries, up to 2 times: first retry raises max_price by 50%, second retry leaves price alone and tells the model to treat size as a soft preference rather than a hard filter. Re-validates returned IDs against load_listings() after each attempt. If results are still empty after both retries, sets error_message in session and returns immediately, skipping suggest_outfit and create_fit_card entirely. |
| suggest_outfit | Wardrobe is empty | Checked before the call ever happens: if wardrobe["items"] is [], the loop skips suggest_outfit outright rather than calling it and handling a failure response, since there's nothing to pair against. Sets outfit = None and wardrobe_empty = True in session, then proceeds straight to create_fit_card. |
| create_fit_card | Outfit input is missing or incomplete | Treated as an expected state, not an error. create_fit_card still runs with outfit = None and produces a stripped caption built only from selected_item fields (title, price, platform, condition), with no styling line. The loop appends a short note to the final response explaining the pairing was left out, based on whether wardrobe_empty or styling_failed was set earlier in the run. |

---

## Architecture

<!-- Draw a diagram of your agent showing how the components connect:
     User input → Planning Loop → Tools (search_listings, suggest_outfit, create_fit_card)
                                                                          ↕
                                                                   State / Session
     Show what triggers each tool, how state flows between them, and where error paths branch off.
     ASCII art, a Mermaid diagram (https://mermaid.js.org/syntax/flowchart.html), or an embedded
     sketch are all fine. You'll share this diagram with an AI tool when asking it to implement
     the planning loop and each individual tool. -->

     ```mermaid
flowchart TD
    A["User query<br/>description, size, max_price, wardrobe"] --> B["search_listings(description, size, max_price)"]
    B --> C["Validate returned IDs against load_listings()<br/>drop unknown IDs"]
    C --> D{"results empty?"}
    D -->|empty, retries remain| E["Loosen constraint, retry_count += 1<br/>retry 1: increase max_price by 50%<br/>retry 2: treat size as soft preference"]
    E --> B
    D -->|empty, retries exhausted| F["ERROR<br/>Session.error_message = 'no listings found'"]
    F --> G(["RETURN error_message"])
    D -->|results found| H["Session.selected_item = results[0]"]
    H --> I{"wardrobe.items empty?"}
    I -->|yes| J["Session.outfit = None<br/>Session.wardrobe_empty = True<br/>suggest_outfit skipped"]
    I -->|no| K["suggest_outfit(selected_item, wardrobe)"]
    K --> L{"exception raised?"}
    L -->|yes| M["Session.outfit = None<br/>Session.styling_failed = True"]
    L -->|no| N{"references wardrobe item<br/>not in wardrobe.items?"}
    N -->|yes, hallucinated| O["Retry once with stricter prompt"]
    O --> P{"still invalid?"}
    P -->|yes| M
    P -->|no, valid| Q["Session.outfit = retry result"]
    N -->|no, valid| R["Session.outfit = outfit_suggestion"]
    J --> S["create_fit_card(outfit, selected_item)"]
    M --> S
    Q --> S
    R --> S
    S --> T{"exception raised?"}
    T -->|yes| U["DEGRADED<br/>Session.degraded_output = True<br/>fit_card = raw selected_item fields + raw outfit text"]
    U --> V(["RETURN degraded_output"])
    T -->|no| W["Session.final_caption = caption<br/>append note if wardrobe_empty or styling_failed"]
    W --> X(["RETURN final_caption"])
```

---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**
I'll use Claude for this, one tool at a time rather than all three in one prompt, so each implementation can be checked against its own spec before moving to the next. For search_listings, I'll give Claude the Tool 1 block from planning.md (the parameter list, return shape, and the failure-mode note about size strings being inconsistent and brand being null on most listings) plus the actual listings.json sample, and ask it to implement the function as an LLM call that ranks by relevance, enforces max_price as a hard filter in code, and returns IDs that I then validate against load_listings(). Before trusting it, I'll check that the generated code never does exact-string matching on size, that max_price filtering happens outside the LLM call, and that there's an explicit step dropping any returned ID not present in load_listings(). Then I'll run it against 3 queries: one that should clearly match, one with a size string in a different format than the listing's (to confirm it's not doing literal equality), and one with a max_price low enough that everything should get excluded.
For suggest_outfit, I'll give Claude the Tool 2 block plus the wardrobe_schema.json example, and ask it to implement the pairing call along with the validation step that checks any wardrobe item the model names actually exists in wardrobe["items"]. I'll verify by checking that the empty-wardrobe case is handled before the LLM call even fires (not inside a try/except after the fact), and that the retry-once-on-hallucination logic is present as a separate branch from the general exception handler. Test cases: the example wardrobe with a clearly compatible new item, the empty wardrobe template, and a wardrobe where nothing shares category or color with the new item.
For create_fit_card, I'll give Claude the Tool 3 block and ask it to implement the caption generator along with the stripped-caption fallback when outfit is None. I'll check that the function doesn't assume outfit is always a string, since None is an expected input, not an exception case. Test cases: a full outfit string and item, an item with outfit=None, and confirming the stripped fallback doesn't reference styling language it wasn't given.

**Milestone 4 — Planning loop and state management:**
I'll give Claude the Architecture diagram, the State Management section, and the Error Handling table together in one prompt, since the loop's correctness depends on all three lining up rather than any one of them in isolation. I'll ask it to implement the loop as a function that builds the session dict once at the top, calls the three tools in sequence with the exact branch logic from the diagram (the two-retry cap in step one, the wardrobe-empty skip in step two, the hallucination retry-once in step two, the exception-to-degraded-output path in step three), and returns one of the three terminal states.
Before trusting the output, I'll trace it line by line against the diagram rather than just running it: confirm retry_count is checked before any retry and incremented after, confirm the wardrobe-empty check happens before suggest_outfit is ever called rather than inside a catch block, and confirm there's no code path that loops back to step one once step two or three has started. Then I'll test four scenarios end to end: a normal run that should produce a final_caption, a query that should exhaust both retries and return error_message, an empty-wardrobe run that should skip suggest_outfit and still produce a stripped caption with the explanatory note, and a forced exception in create_fit_card to confirm degraded_output returns the raw fields instead of crashing the loop.

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
<!-- What does the agent do first? Which tool is called? With what input? -->
The agent calls search_listings("vintage graphic tee", max_price=30.0). It filters the listings catalog by query keywords, price cap, and any inferred style tags like "vintage" or "graphic." Returns the top 3 matches sorted by relevance, i.e. the top result is "Faded Band Tee — $22, Depop, Good condition."

**Step 2:**
<!-- What happens next? What was returned from step 1? What tool is called now? -->
The agent calls suggest_outfit(new_item=<band tee>, wardrobe=<user's wardrobe>). It pulls the user's wardrobe items and pairs the tee with the most compatible pieces, such as the baggy jeans and chunky sneakers the user mentioned. Returns a styled recommendation: "Pair this with your wide-leg jeans and chunky sneakers. Roll the sleeves once and tuck the front corner for shape."

**Step 3:**
<!-- Continue until the full interaction is complete -->
The agent calls create_fit_card(outfit=<suggestion>, new_item=<band tee>). It takes the outfit details and writes a caption. Returns: "thrifted this faded band tee off depop for $22 and it was made for my wide-legs 🖤 full look in my stories."

**Final output to user:**
<!-- What does the user actually see at the end? -->
The user sees the top listing (item name, price, platform, condition), the outfit suggestion telling them exactly how to wear it, and the ready-to-post caption.