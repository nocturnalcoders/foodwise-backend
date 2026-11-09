"""
Database tables. Field names match the React app (see API.md).

Each food table has two classes:
  - XxxIn:  the fields the app sends and receives
  - Xxx:    the database table (adds household_id, which the app never sees)
"""
import uuid
from datetime import date, datetime, timezone
from typing import Literal, Optional

from pydantic import field_validator
from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def new_id() -> str:
    return uuid.uuid4().hex


# ---------- accounts ----------
class Household(SQLModel, table=True):
    __tablename__ = "households"
    id: str = Field(default_factory=new_id, primary_key=True)
    name: str = Field(max_length=60)
    code: str = Field(index=True, unique=True, max_length=6)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class User(SQLModel, table=True):
    __tablename__ = "users"
    id: str = Field(default_factory=new_id, primary_key=True)
    name: str = Field(max_length=60)
    email: str = Field(index=True, unique=True, max_length=200)
    password_hash: str
    household_id: Optional[str] = Field(default=None, foreign_key="households.id", index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------- food data ----------
class ItemIn(SQLModel):
    id: str = Field(primary_key=True, min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=80)
    cat: Literal["fridge", "freezer", "pantry"] = "fridge"
    exp: date
    qty: str = Field(default="1 pcs", max_length=30)
    pct: int = Field(default=100, ge=0, le=100)
    em: str = Field(default="🍽️", max_length=8)
    added: date = Field(default_factory=date.today)


class Item(ItemIn, table=True):
    __tablename__ = "items"
    cat: str = "fridge"
    household_id: str = Field(foreign_key="households.id", index=True)


class ShopIn(SQLModel):
    id: str = Field(primary_key=True, min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=80)
    done: bool = False


class Shop(ShopIn, table=True):
    __tablename__ = "shop"
    household_id: str = Field(foreign_key="households.id", index=True)


class MealIn(SQLModel):
    id: str = Field(primary_key=True, min_length=1, max_length=40)
    date: date
    rid: str = Field(min_length=1, max_length=40)


class Meal(MealIn, table=True):
    __tablename__ = "meals"
    household_id: str = Field(foreign_key="households.id", index=True)


class WasteIn(SQLModel):
    id: str = Field(primary_key=True, min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=80)
    kg: float = Field(gt=0, le=100)
    date: date
    reason: str = Field(default="Expired", max_length=60)


class Waste(WasteIn, table=True):
    __tablename__ = "waste"
    household_id: str = Field(foreign_key="households.id", index=True)


class SavedIn(SQLModel):
    id: str = Field(primary_key=True, min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=80)
    kg: float = Field(gt=0, le=100)
    date: date


class Saved(SavedIn, table=True):
    __tablename__ = "saved"
    household_id: str = Field(foreign_key="households.id", index=True)


class RecipeIn(SQLModel):
    id: str = Field(primary_key=True, min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=80)
    em: str = Field(default="✨", max_length=8)
    min: int = Field(default=30, ge=0, le=600)
    ing: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    steps: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    ai: bool = True

    @field_validator("ing", "steps")
    @classmethod
    def short_list(cls, v: list[str]) -> list[str]:
        return [str(x)[:200] for x in v[:20]]


class Recipe(RecipeIn, table=True):
    __tablename__ = "recipes"
    household_id: str = Field(foreign_key="households.id", index=True)


# collection name in the URL -> (input schema, table)
COLLECTIONS = {
    "items": (ItemIn, Item),
    "shop": (ShopIn, Shop),
    "meals": (MealIn, Meal),
    "waste": (WasteIn, Waste),
    "saved": (SavedIn, Saved),
    "recipes": (RecipeIn, Recipe),
}
