"""Calls Gemini or the Claude API for photo scan and recipe ideas. The API key stays on the server."""
import base64
import io
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError

from .config import ANTHROPIC_API_KEY, CLAUDE_MODEL, GEMINI_API_KEY, GEMINI_MODEL

UNITS = {"pcs", "pack", "L", "ml", "kg", "g"}
CATS = {"fridge", "freezer", "pantry"}


def clean(v, n: int = 60) -> str:
    return re.sub(r"[<>`$\\]", "", str(v or "")).strip()[:n]


def today_sg() -> str:
    return datetime.now(ZoneInfo("Asia/Singapore")).date().isoformat()


def ask_ai(content: list) -> dict:
    """content uses Claude's block format; Gemini is used when GEMINI_API_KEY is set."""
    if GEMINI_API_KEY:
        return ask_gemini(content)
    if ANTHROPIC_API_KEY:
        return ask_claude(content)
    raise HTTPException(503, "AI features are not set up yet.")


def read_json(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    try:
        return json.loads(text[start:end + 1])
    except (ValueError, json.JSONDecodeError):
        print("Unreadable AI reply:", text[:500])
        raise HTTPException(502, "The AI reply could not be read. Try again.")


def ask_gemini(content: list, max_tokens: int = 2000) -> dict:
    parts = [{"type": "text", "text": b["text"]} if b["type"] == "text" else
             {"type": "image", "data": b["source"]["data"], "mime_type": b["source"]["media_type"]}
             for b in content]
    try:
        r = httpx.post(
            "https://generativelanguage.googleapis.com/v1beta/interactions",
            headers={"x-goog-api-key": GEMINI_API_KEY, "content-type": "application/json"},
            json={"model": GEMINI_MODEL, "store": False, "input": parts,
                  "generation_config": {"max_output_tokens": max_tokens}},
            timeout=60,
        )
    except httpx.HTTPError:
        raise HTTPException(502, "The AI service is unavailable. Try again later.")
    if r.status_code in (429, 503):
        raise HTTPException(503, "The AI is busy right now. Try again in a minute.")
    if r.status_code != 200:
        print("Gemini API error", r.status_code, r.text[:500])
        raise HTTPException(502, "The AI service is unavailable. Try again later.")
    text = "".join(c.get("text", "") for s in r.json().get("steps", []) if s.get("type") == "model_output"
                   for c in s.get("content", []) if c.get("type") == "text")
    return read_json(text)


def ask_claude(content: list, max_tokens: int = 2000) -> dict:
    try:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            # Low effort keeps replies fast and cheap; max_tokens leaves room for the model's thinking before the JSON
            json={"model": CLAUDE_MODEL, "max_tokens": max_tokens, "output_config": {"effort": "low"},
                  "messages": [{"role": "user", "content": content}]},
            timeout=60,
        )
    except httpx.HTTPError:
        raise HTTPException(502, "The AI service is unavailable. Try again later.")
    if r.status_code in (429, 529):
        raise HTTPException(503, "The AI is busy right now. Try again in a minute.")
    if r.status_code != 200:
        print("Claude API error", r.status_code, r.text[:500])
        raise HTTPException(502, "The AI service is unavailable. Try again later.")
    text = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
    return read_json(text)


def shrink_photo(raw: bytes) -> str:
    """Resizes any phone photo to max 1568 px JPEG (smaller, cheaper, within API limits)."""
    try:
        img = Image.open(io.BytesIO(raw))
        img = img.convert("RGB")
    except (UnidentifiedImageError, OSError):
        raise HTTPException(415, "That file isn’t a photo we can read. Use a JPG or PNG.")
    img.thumbnail((1568, 1568))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85)
    return base64.b64encode(out.getvalue()).decode()


def scan_photo(raw: bytes) -> dict:
    image = shrink_photo(raw)
    r = ask_ai([
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image}},
        {"type": "text", "text": f"""This photo comes from a household food inventory app in Singapore. Today is {today_sg()}.
Identify the main food item. The photo may show the food itself, its packaging, a label or a barcode.
Reply with only JSON, no other text:
{{"name": "short common English name such as Milk, or null if there is no food",
 "category": "fridge" | "freezer" | "pantry",
 "expiry_date": "YYYY-MM-DD if a use-by, best-before or expiry date is printed and readable, otherwise null",
 "shelf_life_days": typical number of days until it should be used, if no date is readable,
 "quantity": number,
 "unit": "pcs" | "pack" | "L" | "ml" | "kg" | "g"}}"""},
    ])

    exp = r.get("expiry_date")
    exp = exp if isinstance(exp, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", exp) else None

    def to_int(v, default):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return default

    return {
        "name": clean(r.get("name"), 40) or None,
        "category": r.get("category") if r.get("category") in CATS else "fridge",
        "expiry_date": exp,
        "shelf_life_days": max(1, min(730, to_int(r.get("shelf_life_days"), 7))),
        "quantity": max(1, to_int(r.get("quantity"), 1)),
        "unit": r.get("unit") if r.get("unit") in UNITS else "pcs",
    }


def suggest_recipe(items: list[dict]) -> dict:
    lines = "\n".join(
        f"- {clean(i.get('name'), 40)} ({int(i.get('pct') or 0)}% left, {int(i.get('days_left') or 0)} days to expiry)"
        for i in items[:60]
    )
    r = ask_ai([{"type": "text", "text": f"""You help a Singapore household reduce food waste. Their food at home, soonest expiry first:
{lines}

Suggest ONE simple home recipe (40 minutes or less) that uses as many of the soonest-expiring items as possible, plus common staples.
Reply with only JSON, no other text:
{{"name": "...", "emoji": "one food emoji", "minutes": 25,
 "ingredients": ["short lowercase ingredient names such as chicken, lettuce"],
 "steps": ["4 to 6 short steps"]}}"""}])

    if not r.get("name") or not isinstance(r.get("ingredients"), list):
        raise HTTPException(502, "The AI reply could not be read. Try again.")
    try:
        minutes = int(float(r.get("minutes") or 30))
    except (TypeError, ValueError):
        minutes = 30
    return {
        "name": clean(r["name"], 60),
        "emoji": clean(r.get("emoji"), 4) or "✨",
        "minutes": max(5, min(180, minutes)),
        "ingredients": [clean(x, 30).lower() for x in r["ingredients"][:10] if clean(x, 30)],
        "steps": [clean(x, 200) for x in (r.get("steps") or [])[:8] if clean(x, 200)],
    }
