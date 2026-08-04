from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get database URL from environment variable, fallback to SQLite for local development
SQLALCHEMY_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite:///./telecom_sites.db"
)

if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
else:
    # For PostgreSQL (Neon), remove sqlite-specific connect_args
    engine = create_engine(SQLALCHEMY_DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency to get a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate_schema():
    """
    Run ALTER TABLE statements to add new columns to existing tables
    for the Neon PostgreSQL database. Each column is added only if it
    doesn't already exist (PostgreSQL does not support IF NOT EXISTS
    for ADD COLUMN in older versions, so we check information_schema).
    """
    from sqlalchemy.inspection import inspect

    inspector = inspect(engine)
    existing_columns = {}

    for table_name in ["sites", "activities", "company_settings"]:
        try:
            existing_columns[table_name] = {
                col["name"] for col in inspector.get_columns(table_name)
            }
        except Exception:
            existing_columns[table_name] = set()
            print(f"⚠️ Table '{table_name}' not found yet - it will be created by create_all")

    with engine.begin() as conn:
        # --- SITES table additions ---
        site_additions = {
            "site_code": "VARCHAR(100)",
            "site_type": "VARCHAR(50)",
            "region": "VARCHAR(255)",
            "location": "VARCHAR(255)",
            "latitude": "DOUBLE PRECISION",
            "longitude": "DOUBLE PRECISION",
            "google_maps_url": "TEXT",
            "images": "TEXT",
            "notes": "TEXT",
            "is_archived": "BOOLEAN DEFAULT FALSE",
            "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        }
        for col_name, col_def in site_additions.items():
            if col_name not in existing_columns.get("sites", set()):
                conn.execute(text(f'ALTER TABLE sites ADD COLUMN "{col_name}" {col_def}'))
                print(f"✅ Added column sites.{col_name}")

        # --- ACTIVITIES table additions ---
        activity_additions = {
            "activity_date": "TIMESTAMP",
            "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        }
        for col_name, col_def in activity_additions.items():
            if col_name not in existing_columns.get("activities", set()):
                conn.execute(text(f'ALTER TABLE activities ADD COLUMN "{col_name}" {col_def}'))
                print(f"✅ Added column activities.{col_name}")


def init_db():
    """Create all tables and run migrations."""
    import models  # noqa: F401 - ensures models are registered with Base
    Base.metadata.create_all(bind=engine)
    if not SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
        migrate_schema()
    print("✅ Database initialized (tables + migrations complete)")