"""Passwords (bcrypt) and login tokens (JWT)."""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException
from sqlmodel import Session

from .config import JWT_SECRET, TOKEN_DAYS
from .database import get_session
from .models import User


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt()).decode()


def check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode()[:72], hashed.encode())


def make_token(user_id: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=TOKEN_DAYS)
    return jwt.encode({"sub": user_id, "exp": exp}, JWT_SECRET, algorithm="HS256")


def current_user(authorization: str = Header(default=""), session: Session = Depends(get_session)) -> User:
    """Reads 'Authorization: Bearer <token>' and returns the logged-in user."""
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(401, "Please log in first.")
    try:
        user_id = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])["sub"]
    except jwt.PyJWTError:
        raise HTTPException(401, "Your session has expired. Please log in again.")
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(401, "Your account was not found. Please log in again.")
    return user
