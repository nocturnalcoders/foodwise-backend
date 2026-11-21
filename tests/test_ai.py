"""AI endpoints with a fake Claude reply (no API key or internet needed)."""
import io
import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "ai.db")

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app import ai  # noqa: E402
from app.main import app  # noqa: E402


class FakeReply:
    status_code = 200
    def __init__(self, text): self._t = text
    def json(self): return {"content": [{"type": "text", "text": self._t}]}


def test_ai(monkeypatch):
    monkeypatch.setattr(ai, "ANTHROPIC_API_KEY", "test")
    with TestClient(app) as c:
        tok = c.post("/api/auth/register", json={"name": "A", "email": "a@x.com", "password": "secret123"}).json()["token"]
        h = {"Authorization": "Bearer " + tok}

        monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeReply('Here: {"name":"Milk<script>","category":"fridge","expiry_date":null,"shelf_life_days":"5","quantity":1,"unit":"L"}'))
        buf = io.BytesIO(); Image.new("RGB", (3000, 2000), "white").save(buf, "PNG")
        r = c.post("/api/ai/scan", files={"photo": ("p.png", buf.getvalue(), "image/png")}, headers=h)
        assert r.status_code == 200, r.text
        assert r.json() == {"name": "Milkscript", "category": "fridge", "expiry_date": None, "shelf_life_days": 5, "quantity": 1, "unit": "L"}

        r = c.post("/api/ai/scan", files={"photo": ("x.txt", b"not an image", "text/plain")}, headers=h)
        assert r.status_code == 415

        monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeReply('```json\n{"name":"Lettuce Bowl","emoji":"🥗","minutes":20,"ingredients":["Chicken","lettuce"],"steps":["Cook","Serve"]}\n```'))
        r = c.post("/api/ai/recipe", json={"items": [{"name": "Lettuce", "pct": 100, "days_left": 1}]}, headers=h)
        assert r.status_code == 200 and r.json()["ingredients"] == ["chicken", "lettuce"]


class FakeGemini:
    status_code = 200
    def __init__(self, text): self._t = text
    def json(self): return {"steps": [{"type": "thought"}, {"type": "model_output", "content": [{"type": "text", "text": self._t}]}]}


def test_gemini(monkeypatch):
    monkeypatch.setattr(ai, "GEMINI_API_KEY", "test")
    sent = {}
    def fake_post(url, **k):
        sent.update(url=url, body=k["json"])
        return FakeGemini('{"name":"Egg Fried Rice","emoji":"🍳","minutes":15,"ingredients":["egg","rice"],"steps":["Fry"]}')
    with TestClient(app) as c:
        tok = c.post("/api/auth/register", json={"name": "G", "email": "g@x.com", "password": "secret123"}).json()["token"]
        h = {"Authorization": "Bearer " + tok}
        monkeypatch.setattr(httpx, "post", fake_post)
        r = c.post("/api/ai/recipe", json={"items": [{"name": "Egg", "pct": 100, "days_left": 1}]}, headers=h)
        assert r.status_code == 200 and r.json()["name"] == "Egg Fried Rice"
        assert sent["url"].endswith("/interactions") and sent["body"]["input"][0]["type"] == "text"

        buf = io.BytesIO(); Image.new("RGB", (50, 50), "white").save(buf, "PNG")
        c.post("/api/ai/scan", files={"photo": ("p.png", buf.getvalue(), "image/png")}, headers=h)
        assert sent["body"]["input"][0] == {"type": "image", "data": sent["body"]["input"][0]["data"], "mime_type": "image/jpeg"}
