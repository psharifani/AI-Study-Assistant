from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import DATABASE_URL, DATA_DIR, UPLOADS_DIR


class Base(DeclarativeBase):
    pass


engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _migrate_flashcards_sm2_sync(connection) -> None:
    r = connection.execute(text("PRAGMA table_info(flashcards)"))
    cols = {row[1] for row in r.fetchall()}
    if "sm2_ease_factor" not in cols:
        connection.execute(text("ALTER TABLE flashcards ADD COLUMN sm2_ease_factor REAL DEFAULT 2.5"))
    if "sm2_interval_days" not in cols:
        connection.execute(text("ALTER TABLE flashcards ADD COLUMN sm2_interval_days REAL DEFAULT 0"))
    if "sm2_repetitions" not in cols:
        connection.execute(text("ALTER TABLE flashcards ADD COLUMN sm2_repetitions INTEGER DEFAULT 0"))
    if "sm2_next_review_at" not in cols:
        connection.execute(text("ALTER TABLE flashcards ADD COLUMN sm2_next_review_at TIMESTAMP"))


def _migrate_documents_name_sync(connection) -> None:
    r = connection.execute(text("PRAGMA table_info(documents)"))
    cols = {row[1] for row in r.fetchall()}
    if "name" not in cols:
        connection.execute(text("ALTER TABLE documents ADD COLUMN name VARCHAR(200)"))
        connection.execute(text("UPDATE documents SET name = filename WHERE name IS NULL OR TRIM(COALESCE(name,'')) = ''"))


async def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_flashcards_sm2_sync)
        await conn.run_sync(_migrate_documents_name_sync)


async def get_session():
    async with AsyncSessionLocal() as session:
        yield session
