from sqlalchemy import create_engine, event, text
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
# Heroku/Render-style URLs use the deprecated "postgres://" scheme, which
# SQLAlchemy 2.x refuses. Normalise it so either form works.
if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = "postgresql://" + SQLALCHEMY_DATABASE_URL[len("postgres://"):]

IS_SQLITE = SQLALCHEMY_DATABASE_URL.startswith("sqlite")

if IS_SQLITE:
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record):
        # WAL lets reads run while a write is in progress; NORMAL sync is safe
        # with WAL and much faster than the default FULL.
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()
else:
    # PostgreSQL (Neon). Opening a TLS connection to a remote database costs
    # several round trips, so keep a warm pool and reuse connections:
    # - pool_pre_ping drops connections Neon closed while its compute slept,
    #   instead of failing the user's request with "SSL connection closed".
    # - pool_recycle stays under Neon's idle timeout.
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        pool_size=int(os.environ.get("DB_POOL_SIZE", "5")),
        max_overflow=int(os.environ.get("DB_MAX_OVERFLOW", "10")),
        pool_pre_ping=True,
        pool_recycle=280,
        pool_use_lifo=True,  # reuse the hottest connection; lets extras idle out
        connect_args={"connect_timeout": 10, "application_name": "tsm-backend"},
    )

# expire_on_commit=False: after commit we serialize the objects we just wrote;
# without this every attribute access re-SELECTs the row.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine)

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
    for both PostgreSQL and SQLite databases.
    """
    from sqlalchemy.inspection import inspect

    inspector = inspect(engine)
    existing_columns = {}
    is_sqlite = IS_SQLITE

    for table_name in ["sites", "activities", "company_settings", "users"]:
        try:
            existing_columns[table_name] = {
                col["name"] for col in inspector.get_columns(table_name)
            }
        except Exception:
            existing_columns[table_name] = set()
            print(f"⚠️ Table '{table_name}' not found yet - it will be created by create_all")

    with engine.begin() as conn:
        # --- SITES table additions ---
        if is_sqlite:
            site_additions = {
                "site_code": "VARCHAR(100)",
                "site_type": "VARCHAR(50)",
                "region": "VARCHAR(255)",
                "location": "VARCHAR(255)",
                "latitude": "REAL",
                "longitude": "REAL",
                "google_maps_url": "TEXT",
                "images": "TEXT",
                "notes": "TEXT",
                "is_archived": "BOOLEAN DEFAULT 0",
                "created_at": "DATETIME DEFAULT CURRENT_TIMESTAMP",
                "updated_at": "DATETIME DEFAULT CURRENT_TIMESTAMP",
            }
        else:
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
        if is_sqlite:
            activity_additions = {
                "activity_date": "DATETIME",
                "completed_at": "DATETIME",
                "start_datetime": "DATETIME",
                "end_datetime": "DATETIME",
                "created_at": "DATETIME DEFAULT CURRENT_TIMESTAMP",
                "updated_at": "DATETIME DEFAULT CURRENT_TIMESTAMP",
                "is_archived": "BOOLEAN DEFAULT 0",
            }
        else:
            activity_additions = {
                "activity_date": "TIMESTAMP",
                "completed_at": "TIMESTAMP",
                "start_datetime": "TIMESTAMP",
                "end_datetime": "TIMESTAMP",
                "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
                "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
                "is_archived": "BOOLEAN DEFAULT FALSE",
            }
        for col_name, col_def in activity_additions.items():
            if col_name not in existing_columns.get("activities", set()):
                conn.execute(text(f'ALTER TABLE activities ADD COLUMN "{col_name}" {col_def}'))
                print(f"✅ Added column activities.{col_name}")

        # --- USERS table additions ---
        if is_sqlite:
            user_additions = {
                "username": "VARCHAR(100) UNIQUE NOT NULL",
                "email": "VARCHAR(255) UNIQUE",
                "hashed_password": "VARCHAR(255) NOT NULL",
                "role": "VARCHAR(20) DEFAULT 'manager'",
                "is_active": "BOOLEAN DEFAULT 1",
                "created_at": "DATETIME DEFAULT CURRENT_TIMESTAMP",
                "updated_at": "DATETIME DEFAULT CURRENT_TIMESTAMP",
            }
        else:
            user_additions = {
                "username": "VARCHAR(100) UNIQUE NOT NULL",
                "email": "VARCHAR(255) UNIQUE",
                "hashed_password": "VARCHAR(255) NOT NULL",
                "role": "VARCHAR(20) DEFAULT 'manager'",
                "is_active": "BOOLEAN DEFAULT TRUE",
                "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
                "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            }
        for col_name, col_def in user_additions.items():
            if col_name not in existing_columns.get("users", set()):
                conn.execute(text(f'ALTER TABLE users ADD COLUMN "{col_name}" {col_def}'))
                print(f"✅ Added column users.{col_name}")


# Foreign keys are not indexed automatically in PostgreSQL. Without these,
# loading a site's materials/activities/costs is a full table scan each time.
_INDEXES = {
    "ix_materials_site_id": "materials (site_id)",
    "ix_activities_site_id": "activities (site_id)",
    "ix_operational_costs_site_id": "operational_costs (site_id)",
    "ix_sites_is_archived": "sites (is_archived)",
    "ix_users_email_lower": "users (lower(email))",
}


def ensure_indexes():
    with engine.begin() as conn:
        for name, target in _INDEXES.items():
            try:
                conn.execute(text(f"CREATE INDEX IF NOT EXISTS {name} ON {target}"))
            except Exception as e:  # never block startup on an index
                print(f"[WARN] Could not create index {name}: {e}")


def init_db():
    """Create all tables and run migrations."""
    import models  # noqa: F401 - ensures models are registered with Base
    Base.metadata.create_all(bind=engine)
    migrate_schema()
    ensure_indexes()
    print("[OK] Database initialized (tables + migrations complete)")