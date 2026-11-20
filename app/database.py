from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from .config import DATABASE_URL

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)


def create_tables() -> None:
    from . import models  # noqa: F401  (registers the tables)
    SQLModel.metadata.create_all(engine)
    add_missing_columns()


def add_missing_columns() -> None:
    """create_all() never changes existing tables, so new nullable columns are added here."""
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have or not col.nullable:
                    continue
                kind = col.type.compile(dialect=engine.dialect)
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {kind}'))
                if col.unique:
                    conn.execute(text(f'CREATE UNIQUE INDEX IF NOT EXISTS "ix_{table.name}_{col.name}" '
                                      f'ON "{table.name}" ("{col.name}")'))


def get_session():
    with Session(engine) as session:
        yield session
