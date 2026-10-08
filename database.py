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
# Use the psycopg 3 driver for every Postgres URL, whatever scheme it was
# written with ("postgres://", "postgresql://", "postgresql+psycopg2://").
# psycopg 3 ships wheels for current Python versions (incl. 3.14 on Render).
for _prefix in ("postgresql+psycopg2://", "postgresql+psycopg://", "postgresql://", "postgres://"):
    if SQLALCHEMY_DATABASE_URL.startswith(_prefix):
        SQLALCHEMY_DATABASE_URL = "postgresql+psycopg://" + SQLALCHEMY_DATABASE_URL[len(_prefix):]
        break

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

    for table_name in ["sites", "activities", "materials", "company_settings", "users"]:
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

        # --- MATERIALS table additions ---
        material_additions = {
            "purchase_date": "DATETIME" if is_sqlite else "TIMESTAMP",
            "requestor": "VARCHAR(255)",
            "requestor_department": "VARCHAR(255)",
        }
        for col_name, col_def in material_additions.items():
            if col_name not in existing_columns.get("materials", set()):
                conn.execute(text(f'ALTER TABLE materials ADD COLUMN {"" if is_sqlite else "IF NOT EXISTS "}"{col_name}" {col_def}'))
                print(f"✅ Added column materials.{col_name}")

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


# Any fixed number; workers use it to take turns running start-up setup.
_INIT_LOCK_ID = 727274


def _init_schema():
    import models  # noqa: F401 - ensures models are registered with Base
    Base.metadata.create_all(bind=engine)
    migrate_schema()
    ensure_indexes()


def init_db():
    """Create all tables and run migrations.

    Gunicorn starts several workers at once and each runs this. Without
    coordination two workers race to create the same table or column,
    Postgres rejects the second, that worker crashes, and the whole deploy
    fails. A Postgres advisory lock makes them take turns: the first does
    the work, the rest find everything already in place.
    """
    if IS_SQLITE:
        _init_schema()
    else:
        with engine.connect() as lock_conn:
            lock_conn.execute(text("SELECT pg_advisory_lock(:id)"), {"id": _INIT_LOCK_ID})
            try:
                _init_schema()
            finally:
                lock_conn.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": _INIT_LOCK_ID})
                lock_conn.commit()
    print("[OK] Database initialized (tables + migrations complete)")