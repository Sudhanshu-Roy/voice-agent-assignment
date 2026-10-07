"""
Database configuration and session management for SQLite + SQLAlchemy.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./phone_agent.db")

# SQLite requires check_same_thread=False for multi-threaded FastAPI / async workers
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency to yield database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
