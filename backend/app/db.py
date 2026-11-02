import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import DATABASE_URL

if DATABASE_URL.startswith("sqlite"):
    db_path = DATABASE_URL.replace("sqlite:///", "", 1)
    if not os.path.isabs(db_path):
        db_path = str((Path(__file__).resolve().parent.parent / db_path).resolve())
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
