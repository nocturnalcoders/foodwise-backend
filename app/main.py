"""
FOODWISE API (FastAPI).
Endpoints follow API.md in the React project.
Interactive docs: open /docs in the browser.
"""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field, ValidationError
from sqlmodel import Session, select

from . import ai, households
from .config import ALLOWED_ORIGINS
from .database import create_tables, get_session
from .models import COLLECTIONS, Household, User
from .security import check_password, current_user, hash_password, make_token


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_tables()
    yield


app = FastAPI(title="FOODWISE API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
@app.get("/health")
def health():
    return {"status": "ok", "app": "FOODWISE API"}


# ---------- auth ----------
class LoginIn(BaseModel):
    name: str = Field(default="", max_length=60)
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


def user_json(u: User) -> dict:
    return {"id": u.id, "name": u.name, "email": u.email}


@app.post("/api/auth/login")
def login(body: LoginIn, session: Session = Depends(get_session)):
    """Logs in, or creates the account the first time this email is used."""
    email = body.email.lower()
    user = session.exec(select(User).where(User.email == email)).first()
    if user:
        if not check_password(body.password, user.password_hash):
            raise HTTPException(401, "Wrong password for this email.")
    else:
        if len(body.password) < 6:
            raise HTTPException(400, "Choose a password with at least 6 characters.")
        name = body.name.strip() or email.split("@")[0]
        hh = households.personal(session, name)
        user = User(name=name[:60], email=email, password_hash=hash_password(body.password), household_id=hh.id)
        session.add(user)
        session.commit()
        session.refresh(user)
    return {"user": user_json(user), "token": make_token(user.id)}


@app.get("/api/auth/me")
def me(user: User = Depends(current_user)):
    return user_json(user)


# ---------- household ----------
def my_household(session: Session, user: User) -> Household:
    hh = session.get(Household, user.household_id) if user.household_id else None
    if not hh:  # safety net: give the user a household
        hh = households.personal(session, user.name)
        user.household_id = hh.id
        session.add(user)
        session.commit()
    return hh


class NameIn(BaseModel):
    name: str = Field(default="", max_length=60)


class CodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=6)


@app.get("/api/household")
def get_household(user: User = Depends(current_user), session: Session = Depends(get_session)):
    return households.to_json(session, my_household(session, user))


@app.post("/api/household")
def create_household(body: NameIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    old = user.household_id
    hh = households.create(session, body.name or f"{user.name}’s household")
    user.household_id = hh.id
    session.add(user)
    session.flush()
    households.delete_if_empty(session, old)
    session.commit()
    return households.to_json(session, hh)


@app.post("/api/household/join")
def join_household(body: CodeIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    hh = session.exec(select(Household).where(Household.code == body.code.strip().upper())).first()
    if not hh:
        raise HTTPException(404, "No household found with that code. Check it and try again.")
    if hh.id != user.household_id:
        members = len(households.to_json(session, hh)["members"])
        if members >= 10:
            raise HTTPException(400, "This household already has 10 members.")
        old = user.household_id
        user.household_id = hh.id
        session.add(user)
        session.flush()
        households.delete_if_empty(session, old)
        session.commit()
    return households.to_json(session, hh)


@app.post("/api/household/leave")
def leave_household(user: User = Depends(current_user), session: Session = Depends(get_session)):
    old = user.household_id
    hh = households.personal(session, user.name)
    user.household_id = hh.id
    session.add(user)
    session.flush()
    households.delete_if_empty(session, old)
    session.commit()
    return households.to_json(session, hh)


# ---------- AI ----------
class RecipeRequest(BaseModel):
    items: list[dict] = Field(default_factory=list, max_length=200)


@app.post("/api/ai/scan")
async def ai_scan(photo: UploadFile = File(...), user: User = Depends(current_user)):
    raw = await photo.read(10 * 1024 * 1024 + 1)
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(413, "The photo is too large. Use one under 10 MB.")
    return ai.scan_photo(raw)


@app.post("/api/ai/recipe")
def ai_recipe(body: RecipeRequest, user: User = Depends(current_user)):
    if not body.items:
        raise HTTPException(400, "Add some food to your inventory first.")
    return ai.suggest_recipe(body.items)


# ---------- food data: items, shop, meals, waste, saved, recipes ----------
def tables_for(collection: str):
    if collection not in COLLECTIONS:
        raise HTTPException(404, f"Unknown collection: {collection}")
    return COLLECTIONS[collection]


@app.get("/api/{collection}")
def list_records(collection: str, user: User = Depends(current_user), session: Session = Depends(get_session)):
    schema, table = tables_for(collection)
    hh = my_household(session, user)
    rows = session.exec(select(table).where(table.household_id == hh.id)).all()
    return [schema.model_validate(r, from_attributes=True).model_dump(mode="json") for r in rows]


@app.put("/api/{collection}/{record_id}")
def save_record(collection: str, record_id: str, body: dict,
                user: User = Depends(current_user), session: Session = Depends(get_session)):
    """Creates or replaces one record (the app sends the full object)."""
    schema, table = tables_for(collection)
    try:
        data = schema.model_validate({**body, "id": record_id})
    except ValidationError as e:
        first = e.errors()[0]
        raise HTTPException(422, f"Invalid {'.'.join(map(str, first['loc']))}: {first['msg']}")
    hh = my_household(session, user)
    row = session.get(table, record_id)
    if row and row.household_id != hh.id:
        raise HTTPException(409, "This record belongs to another household.")
    values = data.model_dump()
    if row:
        for k, v in values.items():
            setattr(row, k, v)
    else:
        row = table(**values, household_id=hh.id)
    session.add(row)
    session.commit()
    return data.model_dump(mode="json")


@app.delete("/api/{collection}/{record_id}", status_code=204)
def delete_record(collection: str, record_id: str,
                  user: User = Depends(current_user), session: Session = Depends(get_session)):
    _, table = tables_for(collection)
    hh = my_household(session, user)
    row = session.get(table, record_id)
    if row and row.household_id == hh.id:
        session.delete(row)
        session.commit()
    return Response(status_code=204)
