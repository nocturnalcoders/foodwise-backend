"""Checks Google and Apple sign-in tokens and returns who the user is."""
import httpx
import jwt
from fastapi import HTTPException

from .config import APPLE_CLIENT_ID, GOOGLE_CLIENT_ID

APPLE_ISSUER = "https://appleid.apple.com"
_apple_keys = jwt.PyJWKClient(APPLE_ISSUER + "/auth/keys", cache_keys=True)


def google_profile(access_token: str) -> dict:
    """Takes the access token from Google's popup and returns {sub, email, name, picture}."""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(503, "Google sign-in is not set up on this server.")
    try:
        info = httpx.get("https://oauth2.googleapis.com/tokeninfo",
                         params={"access_token": access_token}, timeout=10)
        if info.status_code != 200:
            raise HTTPException(401, "Google sign-in failed. Please try again.")
        tok = info.json()
        # The token must have been issued to our app, not some other website
        if tok.get("aud") != GOOGLE_CLIENT_ID and tok.get("azp") != GOOGLE_CLIENT_ID:
            raise HTTPException(401, "This Google sign-in was not made for FOODWISE.")
        prof = httpx.get("https://www.googleapis.com/oauth2/v3/userinfo",
                         headers={"Authorization": f"Bearer {access_token}"}, timeout=10).json()
    except httpx.HTTPError:
        raise HTTPException(502, "Could not reach Google. Please try again.")
    if not prof.get("email") or not prof.get("email_verified"):
        raise HTTPException(401, "Your Google account has no verified email.")
    return {"sub": prof["sub"], "email": prof["email"], "name": prof.get("name", ""), "picture": prof.get("picture")}


def apple_profile(id_token: str) -> dict:
    """Takes the id_token from Apple's popup and returns {sub, email}."""
    if not APPLE_CLIENT_ID:
        raise HTTPException(503, "Apple sign-in is not set up on this server.")
    try:
        key = _apple_keys.get_signing_key_from_jwt(id_token).key
        claims = jwt.decode(id_token, key, algorithms=["RS256"], audience=APPLE_CLIENT_ID, issuer=APPLE_ISSUER)
    except jwt.PyJWTError:
        raise HTTPException(401, "Apple sign-in failed. Please try again.")
    if not claims.get("email"):
        raise HTTPException(401, "Apple did not share an email for this account.")
    return {"sub": claims["sub"], "email": claims["email"]}
