from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from backend.config import settings

# For SQLite, check_same_thread=False is needed for multi-threaded FastAPI workers.
connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=settings.DEBUG,
    future=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


def run_migrations(engine) -> None:
    """Ensures existing SQLite databases have required schema additions."""
    with engine.connect() as conn:
        try:
            result = conn.exec_driver_sql("PRAGMA table_info(satellites);")
            columns = [row[1] for row in result.fetchall()]
            if columns and "data_source" not in columns:
                conn.exec_driver_sql("ALTER TABLE satellites ADD COLUMN data_source VARCHAR(32) DEFAULT 'SYNTHETIC';")
                conn.commit()
        except Exception:
            pass

        try:
            result = conn.exec_driver_sql("PRAGMA table_info(conjunctions);")
            columns = [row[1] for row in result.fetchall()]
            if columns:
                if "pc_raw" not in columns:
                    conn.exec_driver_sql("ALTER TABLE conjunctions ADD COLUMN pc_raw FLOAT DEFAULT 0.0;")
                if "pc_ml" not in columns:
                    conn.exec_driver_sql("ALTER TABLE conjunctions ADD COLUMN pc_ml FLOAT DEFAULT 0.0;")
                if "pc_ml_calibrated" not in columns:
                    conn.exec_driver_sql("ALTER TABLE conjunctions ADD COLUMN pc_ml_calibrated FLOAT DEFAULT 0.0;")
                if "ml_available" not in columns:
                    conn.exec_driver_sql("ALTER TABLE conjunctions ADD COLUMN ml_available BOOLEAN DEFAULT 0;")
                if "model_version" not in columns:
                    conn.exec_driver_sql("ALTER TABLE conjunctions ADD COLUMN model_version VARCHAR(32) DEFAULT 'v1.0.0';")
                if "data_source" not in columns:
                    conn.exec_driver_sql("ALTER TABLE conjunctions ADD COLUMN data_source VARCHAR(32) DEFAULT 'real';")
                conn.commit()
        except Exception:
            pass


def get_db() -> Generator[Session, None, None]:
    """Dependency that provides an active SQLAlchemy database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Ensure schema migrations run on database initialization
try:
    run_migrations(engine)
except Exception:
    pass

