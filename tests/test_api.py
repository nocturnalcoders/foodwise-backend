"""Run with: pytest  (uses a temporary SQLite database)"""
import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["ANTHROPIC_API_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def login(c, name, email, pw="secret123"):
    r = c.post("/api/auth/login", json={"name": name, "email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def test_full_flow():
    with TestClient(app) as c:
        assert c.get("/health").json()["status"] == "ok"
        loki = login(c, "Loki", "loki@jcu.edu.sg")
        tyta = login(c, "Tyta", "tyta@jcu.edu.sg")
        eve = login(c, "Eve", "eve@x.com")

        # login again with wrong password
        assert c.post("/api/auth/login", json={"email": "loki@jcu.edu.sg", "password": "nope"}).status_code == 401
        # short password on sign up
        assert c.post("/api/auth/login", json={"email": "new@x.com", "password": "123"}).status_code == 400
        # no token
        assert c.get("/api/items").status_code == 401

        item = {"id": "i1", "name": "Milk", "cat": "fridge", "exp": "2026-11-12", "qty": "1 L", "pct": 60, "em": "🥛", "added": "2026-11-06"}
        r = c.put("/api/items/i1", json=item, headers=loki)
        assert r.status_code == 200 and r.json()["exp"] == "2026-11-12"
        assert c.put("/api/recipes/ai1", json={"id": "ai1", "name": "Bowl", "em": "🥗", "min": 20, "ing": ["chicken"], "steps": ["a"], "ai": True}, headers=loki).status_code == 200
        assert c.put("/api/waste/w1", json={"id": "w1", "name": "Lettuce", "kg": 0.3, "date": "2026-11-09", "reason": "Expired"}, headers=loki).status_code == 200
        assert c.put("/api/meals/m1", json={"id": "m1", "date": "2026-11-10", "rid": "r1"}, headers=loki).status_code == 200
        assert c.put("/api/saved/v1", json={"id": "v1", "name": "Spinach", "kg": 0.3, "date": "2026-11-07"}, headers=loki).status_code == 200
        assert c.put("/api/items/bad", json={**item, "pct": 500}, headers=loki).status_code == 422
        assert c.get("/api/nothing", headers=loki).status_code == 404

        # Eve cannot see or touch Loki's data
        assert c.get("/api/items", headers=eve).json() == []
        assert c.put("/api/items/i1", json={**item, "pct": 0}, headers=eve).status_code == 409
        c.delete("/api/items/i1", headers=eve)
        assert len(c.get("/api/items", headers=loki).json()) == 1

        # Tyta joins Loki's household with the code
        code = c.get("/api/household", headers=loki).json()["code"]
        assert c.post("/api/household/join", json={"code": "ZZZZZZ"}, headers=tyta).status_code == 404
        hh = c.post("/api/household/join", json={"code": code.lower()}, headers=tyta).json()
        assert [m["name"] for m in hh["members"]] == ["Loki", "Tyta"]
        assert c.get("/api/items", headers=tyta).json()[0]["name"] == "Milk"
        c.put("/api/items/i1", json={**item, "pct": 40}, headers=tyta)
        assert c.get("/api/items", headers=loki).json()[0]["pct"] == 40
        assert c.get("/api/recipes", headers=tyta).json()[0]["ing"] == ["chicken"]

        # Tyta leaves: gets a fresh, empty household
        left = c.post("/api/household/leave", headers=tyta).json()
        assert len(left["members"]) == 1 and left["code"] != code
        assert c.get("/api/items", headers=tyta).json() == []

        # delete works
        assert c.delete("/api/items/i1", headers=loki).status_code == 204
        assert c.get("/api/items", headers=loki).json() == []

        # AI is off without a key
        assert c.post("/api/ai/recipe", json={"items": [{"name": "Milk", "pct": 50, "days_left": 2}]}, headers=loki).status_code == 503
