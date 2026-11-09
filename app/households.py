"""Household logic: every user belongs to exactly one household."""
import secrets

from sqlmodel import Session, delete, func, select

from .models import COLLECTIONS, Household, User

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I to avoid confusion


def new_code(session: Session) -> str:
    while True:
        code = "".join(secrets.choice(ALPHABET) for _ in range(6))
        if not session.exec(select(Household).where(Household.code == code)).first():
            return code


def create(session: Session, name: str) -> Household:
    hh = Household(name=name.strip()[:60] or "My household", code=new_code(session))
    session.add(hh)
    session.flush()
    return hh


def personal(session: Session, user_name: str) -> Household:
    return create(session, f"{user_name or 'My'}’s household")


def delete_if_empty(session: Session, household_id: str | None) -> None:
    """Removes a household and its food data once nobody is left in it."""
    if not household_id:
        return
    members = session.exec(select(func.count()).select_from(User).where(User.household_id == household_id)).one()
    if members:
        return
    for _, table in COLLECTIONS.values():
        session.exec(delete(table).where(table.household_id == household_id))
    hh = session.get(Household, household_id)
    if hh:
        session.delete(hh)


def to_json(session: Session, hh: Household) -> dict:
    members = session.exec(select(User).where(User.household_id == hh.id).order_by(User.created_at)).all()
    return {
        "id": hh.id,
        "name": hh.name,
        "code": hh.code,
        "members": [{"id": m.id, "name": m.name} for m in members],
    }
