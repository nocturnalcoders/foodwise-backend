"""Sign up, log in, Google/Apple sign-in and profile photos."""
import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "auth.db")
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from app import main, oauth  # noqa: E402

PHOTO = "data:image/jpeg;base64," + "A" * 100


def bearer(r):
    return {"Authorization": "Bearer " + r.json()["token"]}


def test_register_then_login():
    with TestClient(main.app) as c:
        r = c.post("/api/auth/register", json={"name": "Ana", "email": "Ana@x.com", "password": "secret123"})
        assert r.status_code == 200 and r.json()["user"]["email"] == "ana@x.com"
        assert r.json()["user"]["has_password"] is True
        # same email again
        assert c.post("/api/auth/register", json={"email": "ana@x.com", "password": "secret123"}).status_code == 409
        # login no longer creates accounts
        assert c.post("/api/auth/login", json={"email": "nobody@x.com", "password": "secret123"}).status_code == 404
        assert c.post("/api/auth/login", json={"email": "ana@x.com", "password": "wrong"}).status_code == 401
        assert c.post("/api/auth/login", json={"email": "ANA@x.com", "password": "secret123"}).status_code == 200


def test_profile_photo_and_name():
    with TestClient(main.app) as c:
        h = bearer(c.post("/api/auth/register", json={"name": "Bo", "email": "bo@x.com", "password": "secret123"}))
        r = c.patch("/api/auth/me", json={"name": "Bobby", "avatar": PHOTO}, headers=h)
        assert r.status_code == 200 and r.json()["name"] == "Bobby" and r.json()["avatar"] == PHOTO
        assert c.patch("/api/auth/me", json={"avatar": "javascript:alert(1)"}, headers=h).status_code == 422
        assert c.patch("/api/auth/me", json={"avatar": "data:image/jpeg;base64," + "A" * 500_000}, headers=h).status_code == 422
        assert c.patch("/api/auth/me", json={"avatar": ""}, headers=h).json()["avatar"] is None


def test_item_photo():
    with TestClient(main.app) as c:
        h = bearer(c.post("/api/auth/register", json={"email": "cy@x.com", "password": "secret123"}))
        item = {"id": "p1", "name": "Milk", "exp": "2026-12-01", "photo": PHOTO}
        assert c.put("/api/items/p1", json=item, headers=h).json()["photo"] == PHOTO
        assert c.get("/api/items", headers=h).json()[0]["photo"] == PHOTO
        assert c.put("/api/items/p1", json={**item, "photo": "ftp://x"}, headers=h).status_code == 422


def test_google_creates_then_links(monkeypatch):
    profile = {"sub": "g-123", "email": "dee@gmail.com", "name": "Dee", "picture": "https://lh3.googleusercontent.com/a"}
    monkeypatch.setattr(oauth, "google_profile", lambda token: profile)
    with TestClient(main.app) as c:
        r = c.post("/api/auth/google", json={"access_token": "x" * 20})
        u = r.json()["user"]
        assert r.status_code == 200 and u["name"] == "Dee" and u["google"] and not u["has_password"]
        assert u["avatar"] == profile["picture"]
        # password login explains it is a Google account
        r = c.post("/api/auth/login", json={"email": "dee@gmail.com", "password": "whatever"})
        assert r.status_code == 400 and "Google" in r.json()["detail"]
        # signing in again returns the same account
        assert c.post("/api/auth/google", json={"access_token": "x" * 20}).json()["user"]["id"] == u["id"]

        # an existing email account gets linked instead of duplicated
        reg = c.post("/api/auth/register", json={"email": "eli@x.com", "password": "secret123"}).json()["user"]
        monkeypatch.setattr(oauth, "google_profile", lambda token: {**profile, "sub": "g-9", "email": "eli@x.com"})
        assert c.post("/api/auth/google", json={"access_token": "x" * 20}).json()["user"]["id"] == reg["id"]


def test_apple_and_config(monkeypatch):
    monkeypatch.setattr(oauth, "apple_profile", lambda token: {"sub": "a-1", "email": "fi@privaterelay.appleid.com"})
    with TestClient(main.app) as c:
        assert c.get("/api/auth/config").json() == {"google_client_id": None, "apple_client_id": None}
        r = c.post("/api/auth/apple", json={"id_token": "y" * 20, "name": "Fi"})
        assert r.status_code == 200 and r.json()["user"]["name"] == "Fi" and r.json()["user"]["apple"]


def test_social_off_without_config():
    with TestClient(main.app) as c:
        assert c.post("/api/auth/google", json={"access_token": "x" * 20}).status_code == 503
        assert c.post("/api/auth/apple", json={"id_token": "y" * 20}).status_code == 503
