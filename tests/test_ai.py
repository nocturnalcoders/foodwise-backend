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
        tok = c.post("/api/auth/login", json={"name": "A", "email": "a@x.com", "password": "secret123"}).json()["token"]
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
