import os
from dotenv import load_dotenv

load_dotenv()


def _db_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        return "sqlite:///./foodwise.db"
    # Supabase and most hosts give "postgres://" or "postgresql://"; SQLAlchemy needs the driver name.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


DATABASE_URL = _db_url()
JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-secret-change-me")
TOKEN_DAYS = 30
ALLOWED_ORIGINS = [o.strip() for o in os.getenv(
    "ALLOWED_ORIGINS", "https://foodwise-murex.vercel.app,http://localhost:5173"
).split(",") if o.strip()]
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-5-5").strip()
# Gemini (free tier from aistudio.google.com) is used instead of Claude when its key is set.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()

# Optional: social sign-in. Leave empty to hide that button in the app.
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()  # Web client ID from Google Cloud Console
APPLE_CLIENT_ID = os.getenv("APPLE_CLIENT_ID", "").strip()  # Apple "Services ID", e.g. com.foodwise.web
