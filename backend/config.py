import os
from pathlib import Path

from dotenv import load_dotenv

_backend_dir = Path(__file__).resolve().parent
# override=True: .env wins over empty/mis-set Windows user env vars (common cause of "key not set")
# utf-8-sig: strips BOM if Notepad saved "UTF-8 with BOM"
_env_path = _backend_dir / ".env"


def get_openai_credentials() -> tuple[str, str]:
    """Read API key and model from .env (reload each call — matches what LLM routes use)."""
    load_dotenv(_env_path, override=True, encoding="utf-8-sig")
    key = (os.getenv("OPENAI_API_KEY") or "").strip().strip('"').strip("'")
    model = (os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()
    return key, model


OPENAI_API_KEY, OPENAI_MODEL = get_openai_credentials()

DATA_DIR = Path(__file__).resolve().parent / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
DATABASE_URL = f"sqlite+aiosqlite:///{DATA_DIR / 'study_assistant.db'}"
