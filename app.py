from contextlib import asynccontextmanager
from dotenv import load_dotenv
load_dotenv()

from fastapi import BackgroundTasks, FastAPI, Depends, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timedelta, timezone
from sqlalchemy import case, func
from sqlalchemy.orm import Session, selectinload

from database import SessionLocal, Base, engine, get_db, init_db
from models import Site, Material, Activity, OperationalCost, CompanySetting, PasswordResetToken, User, UserRole
from auth import (
    RESET_TOKEN_TTL_MINUTES,
    ForgotPasswordRequest,
    LoginRequest,
    ResetPasswordRequest,
    SignupRequest,
    Token,
    authenticate_user,
    client_ip,
    create_user,
    disable_legacy_default_users,
    get_current_active_user,
    get_password_hash,
    get_secret_key,
    get_user_by_email,
    get_user_by_username,
    hash_reset_token,
    login_limiter,
    reset_limiter,
    role_for_access_code,
    signup_enabled,
    signup_limiter,
    token_response,
    validate_email,
    validate_password,
    validate_username,
)
from mailer import send_password_reset_email
import random
import secrets
import string
import uuid


# ========== LIFESPAN (async startup/shutdown) ==========
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: run DB init & seeding in background so we don't block the event loop
    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, init_db)
    db = SessionLocal()
    try:
        disable_legacy_default_users(db)
    finally:
        db.close()
    await loop.run_in_executor(None, get_secret_key)  # resolve once, before traffic
    yield
    # Shutdown: nothing special needed


app = FastAPI(title="Telecom Site Backend", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    # NOTE: must be False when using wildcard origins - per fetch spec browsers
    # reject `Access-Control-Allow-Origin: *` on credentialed requests, which
    # surfaces as "No 'Access-Control-Allow-Origin' header" console errors.
    # We use Bearer tokens (not cookies), so credentials are not needed.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Site lists are repetitive JSON; gzip typically shrinks them 80-90%.
app.add_middleware(GZipMiddleware, minimum_size=1024)

# ========== AI ASSISTANT ROUTES ==========
# Mounted defensively: if the AI deps aren't installed the rest of the API must
# still boot. /ai/status reports why the assistant is unavailable.
try:
    from ai.routes import router as ai_router

    app.include_router(ai_router)
except Exception as _ai_import_error:  # pragma: no cover - deployment safety net
    import logging

    logging.getLogger(__name__).warning(
        "AI assistant routes not mounted: %s", _ai_import_error
    )


# ========== PYDANTIC SCHEMAS ==========


class SiteCreate(BaseModel):
    name: str
    laborCost: Optional[float] = 0.0
    siteCode: Optional[str] = None
    siteType: Optional[str] = None
    region: Optional[str] = None
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    googleMapsUrl: Optional[str] = None
    images: Optional[str] = None
    notes: Optional[str] = None
    isArchived: Optional[bool] = False
    createdAt: Optional[datetime] = None  # Editable creation date (defaults to now if omitted)


class SiteUpdate(BaseModel):
    name: Optional[str] = None
    laborCost: Optional[float] = None
    siteCode: Optional[str] = None
    siteType: Optional[str] = None
    region: Optional[str] = None
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    googleMapsUrl: Optional[str] = None
    images: Optional[str] = None
    notes: Optional[str] = None
    isArchived: Optional[bool] = None
    createdAt: Optional[datetime] = None  # Allow editing creation date


class MaterialCreate(BaseModel):
    name: str
    quantity: float
    unit: str
    cost: float


class ActivityCreate(BaseModel):
    name: str
    completed: Optional[bool] = False
    isArchived: Optional[bool] = False
    activityDate: Optional[datetime] = None
    completedAt: Optional[datetime] = None
    startDatetime: Optional[datetime] = None
    endDatetime: Optional[datetime] = None


class ActivityUpdate(BaseModel):
    name: Optional[str] = None
    completed: Optional[bool] = None
    isArchived: Optional[bool] = None
    activityDate: Optional[datetime] = None
    completedAt: Optional[datetime] = None
    startDatetime: Optional[datetime] = None
    endDatetime: Optional[datetime] = None


class OperationalCostCreate(BaseModel):
    name: str
    amount: float


class ImportMaterial(BaseModel):
    name: str
    quantity: Optional[float] = 0.0
    unit: Optional[str] = None
    cost: Optional[float] = 0.0


class ImportActivity(BaseModel):
    name: str
    completed: Optional[bool] = False
    isArchived: Optional[bool] = False
    activityDate: Optional[datetime] = None
    completedAt: Optional[datetime] = None
    startDatetime: Optional[datetime] = None
    endDatetime: Optional[datetime] = None
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None


class ImportOperationalCost(BaseModel):
    name: str
    amount: Optional[float] = 0.0


class ImportSite(BaseModel):
    name: str
    laborCost: Optional[float] = 0.0
    siteCode: Optional[str] = None
    siteType: Optional[str] = None
    region: Optional[str] = None
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    googleMapsUrl: Optional[str] = None
    images: Optional[str] = None
    notes: Optional[str] = None
    isArchived: Optional[bool] = False
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None
    materials: Optional[List[ImportMaterial]] = []
    activities: Optional[List[ImportActivity]] = []
    operationalCosts: Optional[List[ImportOperationalCost]] = []


class ImportPayload(BaseModel):
    sites: List[ImportSite]


class CompanySettingsUpdate(BaseModel):
    name: Optional[str] = None
    logoUrl: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    website: Optional[str] = None


# ========== HELPERS ==========


def generate_site_code(name: str, db: Session) -> str:
    """Generate a site code like TEL-XXXX-1234 based on the site name."""
    prefix = "TEL"
    name_part = "".join(c for c in name.upper() if c.isalnum())[:4]
    if not name_part:
        name_part = "SITE"
    random_part = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    code = f"{prefix}-{name_part}-{random_part}"
    # Ensure uniqueness
    while db.query(Site).filter(Site.site_code == code).first():
        random_part = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
        code = f"{prefix}-{name_part}-{random_part}"
    return code


def serialize_material(m: Material) -> dict:
    return {
        "id": m.id,
        "name": m.name,
        "quantity": m.quantity,
        "unit": m.unit,
        "cost": m.cost,
    }


def serialize_activity(a: Activity) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "completed": a.completed,
        "isArchived": a.is_archived,
        "completedAt": a.completed_at.isoformat() if a.completed_at else None,
        "activityDate": a.activity_date.isoformat() if a.activity_date else None,
        "startDatetime": a.start_datetime.isoformat() if a.start_datetime else None,
        "endDatetime": a.end_datetime.isoformat() if a.end_datetime else None,
        "createdAt": a.created_at.isoformat() if a.created_at else None,
        "updatedAt": a.updated_at.isoformat() if a.updated_at else None,
    }


def serialize_operational_cost(oc: OperationalCost) -> dict:
    return {
        "id": oc.id,
        "name": oc.name,
        "amount": oc.amount,
    }


def sites_with_children(db: Session):
    """Site query that loads materials, activities and costs in 3 batched
    queries total, instead of 3 extra queries *per site* (the N+1 problem that
    made the dashboard slow against a remote database)."""
    return db.query(Site).options(
        selectinload(Site.materials),
        selectinload(Site.activities),
        selectinload(Site.operational_costs),
    )


def get_site_or_404(db: Session, site_id: str, with_children: bool = False) -> Site:
    query = sites_with_children(db) if with_children else db.query(Site)
    site = query.filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    return site


def site_exists_or_404(db: Session, site_id: str):
    if not db.query(Site.id).filter(Site.id == site_id).first():
        raise HTTPException(status_code=404, detail="Site not found")


def serialize_site(site: Site) -> dict:
    operational_costs = [serialize_operational_cost(oc) for oc in site.operational_costs]

    return {
        "id": site.id,
        "name": site.name,
        "laborCost": site.labor_cost,
        "siteCode": site.site_code,
        "siteType": site.site_type,
        "region": site.region,
        "location": site.location,
        "latitude": site.latitude,
        "longitude": site.longitude,
        "googleMapsUrl": site.google_maps_url,
        "images": site.images,
        "notes": site.notes,
        "isArchived": site.is_archived,
        "createdAt": site.created_at.isoformat() if site.created_at else None,
        "updatedAt": site.updated_at.isoformat() if site.updated_at else None,
        "materials": [serialize_material(m) for m in site.materials],
        "activities": [serialize_activity(a) for a in site.activities],
        "operationalCosts": operational_costs,
    }


# ========== HEALTH ROUTE ==========


@app.get("/")
def health():
    return {"message": "✅ Telecom Site Backend is running!"}


@app.get("/healthz")
def healthz():
    """Cheap liveness check for keep-warm pings - doesn't touch the database."""
    return {"ok": True}


# ========== AUTH ROUTES ==========


@app.get("/auth/config")
def auth_config():
    """Public: lets the sign-in screen know whether to offer sign-up."""
    return {"signupEnabled": signup_enabled()}


@app.post("/auth/login", response_model=Token)
def login(login_data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    email = (login_data.email or "").strip().lower()
    login_limiter.check(f"{client_ip(request)}:{email}")
    user = authenticate_user(db, email, login_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="That email and password don't match an account.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="This account is disabled. Contact your administrator.")
    return token_response(user)


@app.post("/auth/signup", response_model=Token, status_code=201)
def signup(data: SignupRequest, request: Request, db: Session = Depends(get_db)):
    signup_limiter.check(client_ip(request))
    if not signup_enabled():
        raise HTTPException(status_code=403, detail="Sign-up is turned off. Ask your administrator for an account.")

    email = validate_email(data.email)
    username = validate_username(data.username)
    password = validate_password(data.password)
    role = role_for_access_code(data.accessCode)
    if not role:
        raise HTTPException(status_code=403, detail="That access phrase isn't valid. Check it with your administrator.")

    if get_user_by_email(db, email):
        raise HTTPException(status_code=409, detail="An account with this email already exists. Sign in instead.")
    if get_user_by_username(db, username):
        raise HTTPException(status_code=409, detail="That username is taken. Pick another.")

    try:
        user = create_user(db, username=username, email=email, password=password, role=role)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email or username already exists.")
    return token_response(user)


@app.post("/auth/forgot-password")
def forgot_password(
    data: ForgotPasswordRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Always answers the same way, so it can't be used to find out which
    emails have accounts. The email is sent in the background."""
    email = (data.email or "").strip().lower()
    reset_limiter.check(f"{client_ip(request)}:{email}")
    generic = {"message": "If an account exists for that email, a reset link is on its way."}

    user = get_user_by_email(db, email) if email else None
    if not user or not user.is_active or not user.email:
        return generic

    now = datetime.now(timezone.utc)
    # Only the newest link works.
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None)
    ).update({PasswordResetToken.used_at: now}, synchronize_session=False)

    raw_token = secrets.token_urlsafe(32)
    db.add(PasswordResetToken(
        user_id=user.id,
        token_hash=hash_reset_token(raw_token),
        expires_at=now + timedelta(minutes=RESET_TOKEN_TTL_MINUTES),
    ))
    db.commit()

    settings = db.query(CompanySetting).filter(CompanySetting.id == "company").first()
    background_tasks.add_task(
        send_password_reset_email,
        user.email,
        user.username,
        raw_token,
        settings.name if settings else None,
        RESET_TOKEN_TTL_MINUTES,
    )
    return generic


@app.post("/auth/reset-password", response_model=Token)
def reset_password(data: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    reset_limiter.check(f"reset:{client_ip(request)}")
    password = validate_password(data.password)
    invalid = HTTPException(
        status_code=400, detail="This reset link is invalid or has expired. Request a new one."
    )

    record = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.token_hash == hash_reset_token(data.token or ""))
        .first()
    )
    if not record or record.used_at is not None:
        raise invalid
    expires_at = record.expires_at
    if expires_at.tzinfo is None:  # SQLite drops tz info
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise invalid

    user = db.get(User, record.user_id)
    if not user or not user.is_active:
        raise invalid

    user.hashed_password = get_password_hash(password)  # also revokes old sessions
    record.used_at = datetime.now(timezone.utc)
    db.commit()
    return token_response(user)


@app.get("/auth/me", response_model=Token)
def get_current_user_info(current_user=Depends(get_current_active_user)):
    role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    return Token(
        access_token="",
        username=current_user.username,
        email=current_user.email,
        role=role,
    )


# ========== SITE ROUTES ==========


@app.get("/sites")
def get_sites(
    include_archived: bool = Query(False, description="Include archived sites"),
    sort_by: Optional[str] = Query(None, description="createdAt, updatedAt, name, siteType, region"),
    sort_order: Optional[str] = Query("desc", description="asc or desc"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    try:
        query = sites_with_children(db)
        if not include_archived:
            query = query.filter(Site.is_archived == False)  # noqa: E712

        sortable_fields = {
            "createdAt": Site.created_at,
            "updatedAt": Site.updated_at,
            "name": Site.name,
            "siteType": Site.site_type,
            "region": Site.region,
        }
        if sort_by in sortable_fields:
            sort_column = sortable_fields[sort_by]
            query = query.order_by(sort_column.asc() if (sort_order or "").lower() == "asc" else sort_column.desc())

        sites = query.all()
        return [serialize_site(site) for site in sites]
    except Exception as e:
        print(f"❌ Error in get_sites: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch sites: {str(e)}")


@app.get("/sites/stats")
def get_site_stats(
    include_archived: bool = Query(False, description="Include archived sites in stats"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    # Totals are computed by the database in 4 small queries instead of
    # loading every site with every child row.
    site_query = db.query(Site.id, Site.labor_cost, Site.created_at)
    if not include_archived:
        site_query = site_query.filter(Site.is_archived == False)  # noqa: E712
    sites = site_query.all()

    archived_sites = db.query(func.count(Site.id)).filter(Site.is_archived == True).scalar() or 0  # noqa: E712

    material_totals = dict(
        db.query(Material.site_id, func.coalesce(func.sum(Material.cost), 0.0)).group_by(Material.site_id).all()
    )
    operational_totals = dict(
        db.query(OperationalCost.site_id, func.coalesce(func.sum(OperationalCost.amount), 0.0))
        .group_by(OperationalCost.site_id)
        .all()
    )
    activity_counts = {
        site_id: (total, done or 0)
        for site_id, total, done in db.query(
            Activity.site_id,
            func.count(Activity.id),
            func.sum(case((Activity.completed == True, 1), else_=0)),  # noqa: E712
        )
        .filter(Activity.is_archived == False)  # noqa: E712
        .group_by(Activity.site_id)
        .all()
    }

    total_sites = len(sites)
    completed_sites = 0
    total_labor = 0.0
    total_materials = 0.0
    total_operational = 0.0
    monthly: dict = {}
    yearly: dict = {}

    def bucket(store: dict, key: str):
        return store.setdefault(
            key,
            {"period": key, "laborCost": 0.0, "materialsCost": 0.0, "operationalCost": 0.0, "total": 0.0},
        )

    for site_id, labor_cost, created_at in sites:
        total_acts, done_acts = activity_counts.get(site_id, (0, 0))
        if total_acts and done_acts == total_acts:
            completed_sites += 1

        labor = float(labor_cost or 0.0)
        materials_cost = float(material_totals.get(site_id, 0.0) or 0.0)
        operational_cost = float(operational_totals.get(site_id, 0.0) or 0.0)
        site_total = labor + materials_cost + operational_cost

        total_labor += labor
        total_materials += materials_cost
        total_operational += operational_cost

        month_key = created_at.strftime("%Y-%m") if created_at else "unknown"
        year_key = created_at.strftime("%Y") if created_at else "unknown"

        for store, key in ((monthly, month_key), (yearly, year_key)):
            b = bucket(store, key)
            b["laborCost"] += labor
            b["materialsCost"] += materials_cost
            b["operationalCost"] += operational_cost
            b["total"] += site_total

    completed_percentage = round((completed_sites / total_sites * 100), 1) if total_sites else 0.0

    def rounded(rows: dict) -> list:
        out = []
        for row in sorted(rows.values(), key=lambda r: r["period"]):
            out.append({k: (round(v, 2) if isinstance(v, float) else v) for k, v in row.items()})
        return out

    return {
        "totalSites": total_sites,
        "archivedSites": archived_sites,
        "completedSites": completed_sites,
        "completedPercentage": completed_percentage,
        "expenses": {
            "totalLaborCost": round(total_labor, 2),
            "totalMaterialsCost": round(total_materials, 2),
            "totalOperationalCost": round(total_operational, 2),
            "totalExpenses": round(total_labor + total_materials + total_operational, 2),
            "monthly": rounded(monthly),
            "yearly": rounded(yearly),
        },
    }


@app.get("/sites/export")
def export_sites(
    include_archived: bool = Query(True, description="Include archived sites in export"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    query = sites_with_children(db)
    if not include_archived:
        query = query.filter(Site.is_archived == False)  # noqa: E712
    sites = query.all()
    settings = db.query(CompanySetting).filter(CompanySetting.id == "company").first()

    return {
        "version": "1.0",
        "exportedAt": datetime.now(timezone.utc).isoformat(),
        "companySettings": {
            "name": settings.name,
            "logoUrl": settings.logo_url,
            "email": settings.email,
            "phone": settings.phone,
            "address": settings.address,
            "website": settings.website,
        } if settings else None,
        "sites": [serialize_site(s) for s in sites],
    }


@app.post("/sites/import")
def import_sites(payload: ImportPayload, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    imported_ids = []
    skipped = []

    existing_sites = db.query(Site).all()
    existing_by_code = {s.site_code.strip().lower(): s for s in existing_sites if s.site_code}
    existing_by_name_loc = {
        (s.name.strip().lower(), (s.location or "").strip().lower()): s
        for s in existing_sites
    }

    for site_in in payload.sites:
        code_key = site_in.siteCode.strip().lower() if site_in.siteCode else None
        name_loc_key = (site_in.name.strip().lower(), (site_in.location or "").strip().lower())

        dup = existing_by_code.get(code_key) if code_key else None
        if not dup:
            dup = existing_by_name_loc.get(name_loc_key)

        if dup:
            skipped.append({
                "name": site_in.name,
                "siteCode": site_in.siteCode,
                "reason": f"Duplicate of existing site '{dup.name}' ({dup.id})",
            })
            continue

        now = datetime.now(timezone.utc)
        new_site = Site(
            id=str(uuid.uuid4()),
            name=site_in.name,
            labor_cost=site_in.laborCost or 0.0,
            site_code=site_in.siteCode or generate_site_code(site_in.name, db),
            site_type=site_in.siteType,
            region=site_in.region,
            location=site_in.location,
            latitude=site_in.latitude,
            longitude=site_in.longitude,
            google_maps_url=site_in.googleMapsUrl,
            images=site_in.images,
            notes=site_in.notes,
            is_archived=site_in.isArchived or False,
            created_at=site_in.createdAt or now,
            updated_at=site_in.updatedAt or now,
        )
        db.add(new_site)

        for m in site_in.materials or []:
            db.add(Material(
                id=str(uuid.uuid4()),
                name=m.name,
                quantity=m.quantity or 0.0,
                unit=m.unit,
                cost=m.cost or 0.0,
                site_id=new_site.id,
            ))

        for a in site_in.activities or []:
            db.add(Activity(
                id=str(uuid.uuid4()),
                name=a.name,
                completed=a.completed or False,
                is_archived=a.isArchived or False,
                activity_date=a.activityDate,
                start_datetime=a.startDatetime,
                end_datetime=a.endDatetime,
                completed_at=a.completedAt,
                created_at=a.createdAt or now,
                updated_at=a.updatedAt or now,
                site_id=new_site.id,
            ))

        for oc in site_in.operationalCosts or []:
            db.add(OperationalCost(
                id=str(uuid.uuid4()),
                name=oc.name,
                amount=oc.amount or 0.0,
                site_id=new_site.id,
            ))

        # Dedupe against other rows later in the same payload, not just the DB.
        if new_site.site_code:
            existing_by_code[new_site.site_code.strip().lower()] = new_site
        existing_by_name_loc[(new_site.name.strip().lower(), (new_site.location or "").strip().lower())] = new_site

        imported_ids.append(new_site.id)

    db.commit()

    return {
        "message": f"Imported {len(imported_ids)} sites, skipped {len(skipped)} duplicates",
        "importedCount": len(imported_ids),
        "skippedCount": len(skipped),
        "importedSiteIds": imported_ids,
        "skipped": skipped,
    }


@app.post("/sites/bulk-archive")
def bulk_archive_sites(
    site_ids: List[str],
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Archive multiple sites at once."""
    sites = db.query(Site).filter(Site.id.in_(site_ids)).all()
    if not sites:
        raise HTTPException(status_code=404, detail="No matching sites found")

    for site in sites:
        site.is_archived = True

    db.commit()
    return {"message": f"Archived {len(sites)} sites", "archivedIds": [s.id for s in sites]}


@app.post("/sites/bulk-unarchive")
def bulk_unarchive_sites(
    site_ids: List[str],
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Unarchive multiple sites at once."""
    sites = db.query(Site).filter(Site.id.in_(site_ids)).all()
    if not sites:
        raise HTTPException(status_code=404, detail="No matching sites found")

    for site in sites:
        site.is_archived = False

    db.commit()
    return {"message": f"Unarchived {len(sites)} sites", "unarchivedIds": [s.id for s in sites]}


@app.post("/sites", status_code=201)
def create_site(site_data: SiteCreate, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    try:
        now = datetime.now(timezone.utc)
        new_site = Site(
            id=str(uuid.uuid4()),
            name=site_data.name,
            labor_cost=site_data.laborCost or 0.0,
            site_code=site_data.siteCode or generate_site_code(site_data.name, db),
            site_type=site_data.siteType,
            region=site_data.region,
            location=site_data.location,
            latitude=site_data.latitude,
            longitude=site_data.longitude,
            google_maps_url=site_data.googleMapsUrl,
            images=site_data.images,
            notes=site_data.notes,
            is_archived=site_data.isArchived or False,
            created_at=site_data.createdAt or now,
            updated_at=now,
        )
        db.add(new_site)
        db.commit()
        db.refresh(new_site)
        return serialize_site(new_site)
    except Exception as e:
        db.rollback()
        print(f"❌ Error in create_site: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create site: {str(e)}")


@app.get("/sites/{site_id}")
def get_site(site_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    return serialize_site(get_site_or_404(db, site_id, with_children=True))


@app.put("/sites/{site_id}")
def update_site(site_id: str, site_data: SiteUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    try:
        site = db.query(Site).filter(Site.id == site_id).first()
        if not site:
            raise HTTPException(status_code=404, detail="Site not found")

        data = site_data.model_dump(exclude_unset=True)

        field_mapping = {
            "name": "name",
            "laborCost": "labor_cost",
            "siteCode": "site_code",
            "siteType": "site_type",
            "region": "region",
            "location": "location",
            "latitude": "latitude",
            "longitude": "longitude",
            "googleMapsUrl": "google_maps_url",
            "images": "images",
            "notes": "notes",
            "isArchived": "is_archived",
            "createdAt": "created_at",
        }

        for api_field, db_field in field_mapping.items():
            if api_field in data:
                setattr(site, db_field, data[api_field])

        db.commit()
        db.refresh(site)
        return serialize_site(site)

    except Exception as e:
        db.rollback()
        print("❌ Error in update_site:", str(e))
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}")


@app.delete("/sites/{site_id}")
def delete_site(site_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    db.delete(site)
    db.commit()
    return {"message": "Site deleted"}


@app.post("/sites/{site_id}/archive")
def archive_site(site_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    site.is_archived = True
    db.commit()
    db.refresh(site)
    return serialize_site(site)


@app.post("/sites/{site_id}/unarchive")
def unarchive_site(site_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    site.is_archived = False
    db.commit()
    db.refresh(site)
    return serialize_site(site)


# ========== MATERIAL ROUTES ==========


@app.post("/sites/{site_id}/materials", status_code=201)
def add_material(site_id: str, material_data: MaterialCreate, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    new_material = Material(
        id=str(uuid.uuid4()),
        name=material_data.name,
        quantity=material_data.quantity,
        unit=material_data.unit,
        cost=material_data.cost,
        site_id=site.id,
    )
    db.add(new_material)
    db.commit()
    db.refresh(new_material)
    return serialize_material(new_material)


@app.delete("/sites/{site_id}/materials/{material_id}")
def delete_material(site_id: str, material_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    material = db.query(Material).filter(Material.id == material_id, Material.site_id == site_id).first()
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")

    db.delete(material)
    db.commit()
    return {"message": "Material deleted"}


# ========== ACTIVITY ROUTES ==========


@app.get("/sites/{site_id}/activities")
def get_activities(
    site_id: str,
    sort_by: Optional[str] = "activityDate",
    sort_order: Optional[str] = "desc",
    include_archived: Optional[bool] = False,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user)
):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    # Define sortable fields
    sortable_fields = {
        "activityDate": Activity.activity_date,
        "startDatetime": Activity.start_datetime,
        "endDatetime": Activity.end_datetime,
        "createdAt": Activity.created_at,
        "updatedAt": Activity.updated_at,
        "name": Activity.name,
    }

    sort_column = sortable_fields.get(sort_by, Activity.activity_date)
    query = db.query(Activity).filter(Activity.site_id == site_id)

    # Filter by archive status
    if not include_archived:
        query = query.filter(Activity.is_archived == False)

    if sort_order.lower() == "asc":
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())

    activities = query.all()
    return [serialize_activity(a) for a in activities]


@app.post("/sites/{site_id}/activities", status_code=201)
def add_activity(site_id: str, activity_data: ActivityCreate, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    new_activity = Activity(
        id=str(uuid.uuid4()),
        name=activity_data.name,
        completed=activity_data.completed or False,
        is_archived=activity_data.isArchived or False,
        activity_date=activity_data.activityDate,
        start_datetime=activity_data.startDatetime,
        end_datetime=activity_data.endDatetime,
        completed_at=activity_data.completedAt or (datetime.now(timezone.utc) if activity_data.completed else None),
        site_id=site.id,
    )
    db.add(new_activity)
    db.commit()
    db.refresh(new_activity)
    return serialize_activity(new_activity)


@app.patch("/sites/{site_id}/activities/{activity_id}")
def update_activity(site_id: str, activity_id: str, activity_data: ActivityUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    activity = db.query(Activity).filter(Activity.id == activity_id, Activity.site_id == site_id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    data = activity_data.model_dump(exclude_unset=True)
    if "name" in data:
        activity.name = data["name"]
    if "completed" in data:
        was_completed = activity.completed
        activity.completed = data["completed"]
        # Auto-set completed_at when marking complete; clear when un-completing
        if data["completed"] and not was_completed and "completedAt" not in data:
            activity.completed_at = datetime.now(timezone.utc)
        elif not data["completed"]:
            activity.completed_at = None
    if "completedAt" in data:
        activity.completed_at = data["completedAt"]
    if "activityDate" in data:
        activity.activity_date = data["activityDate"]
    if "startDatetime" in data:
        activity.start_datetime = data["startDatetime"]
    if "endDatetime" in data:
        activity.end_datetime = data["endDatetime"]
    if "isArchived" in data:
        activity.is_archived = data["isArchived"]

    db.commit()
    db.refresh(activity)
    return serialize_activity(activity)


@app.post("/sites/{site_id}/activities/bulk-archive")
def bulk_archive_activities(
    site_id: str,
    activity_ids: List[str],
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user)
):
    """Archive multiple activities at once (scrum-style batch operations)."""
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    activities = db.query(Activity).filter(
        Activity.id.in_(activity_ids),
        Activity.site_id == site_id
    ).all()

    if not activities:
        raise HTTPException(status_code=404, detail="No matching activities found")

    archived_count = 0
    for activity in activities:
        activity.is_archived = True
        archived_count += 1

    db.commit()

    return {"message": f"Archived {archived_count} activities", "archivedIds": [a.id for a in activities]}


@app.post("/sites/{site_id}/activities/bulk-unarchive")
def bulk_unarchive_activities(
    site_id: str,
    activity_ids: List[str],
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user)
):
    """Unarchive multiple activities at once."""
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    activities = db.query(Activity).filter(
        Activity.id.in_(activity_ids),
        Activity.site_id == site_id
    ).all()

    if not activities:
        raise HTTPException(status_code=404, detail="No matching activities found")

    unarchived_count = 0
    for activity in activities:
        activity.is_archived = False
        unarchived_count += 1

    db.commit()

    return {"message": f"Unarchived {unarchived_count} activities", "unarchivedIds": [a.id for a in activities]}


@app.delete("/sites/{site_id}/activities/{activity_id}")
def delete_activity(site_id: str, activity_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    activity = db.query(Activity).filter(Activity.id == activity_id, Activity.site_id == site_id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    db.delete(activity)
    db.commit()
    return {"message": "Activity deleted"}


# ========== OPERATIONAL COST ROUTES ==========


@app.post("/sites/{site_id}/operational-costs", status_code=201)
def add_operational_cost(site_id: str, oc_data: OperationalCostCreate, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    new_oc = OperationalCost(
        id=str(uuid.uuid4()),
        name=oc_data.name,
        amount=oc_data.amount,
        site_id=site.id,
    )
    db.add(new_oc)
    db.commit()
    db.refresh(new_oc)
    return serialize_operational_cost(new_oc)


@app.delete("/sites/{site_id}/operational-costs/{operational_cost_id}")
def delete_operational_cost(site_id: str, operational_cost_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    oc = db.query(OperationalCost).filter(OperationalCost.id == operational_cost_id, OperationalCost.site_id == site_id).first()
    if not oc:
        raise HTTPException(status_code=404, detail="Operational cost not found")

    db.delete(oc)
    db.commit()
    return {"message": "Operational cost deleted"}


# ========== COMPANY SETTINGS ROUTES ==========


@app.get("/company-settings")
def get_company_settings(db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    settings = db.query(CompanySetting).filter(CompanySetting.id == "company").first()
    if not settings:
        # Return defaults if not set yet
        return {
            "id": "company",
            "name": None,
            "logoUrl": None,
            "email": None,
            "phone": None,
            "address": None,
            "website": None,
        }
    return {
        "id": settings.id,
        "name": settings.name,
        "logoUrl": settings.logo_url,
        "email": settings.email,
        "phone": settings.phone,
        "address": settings.address,
        "website": settings.website,
    }


@app.put("/company-settings")
def update_company_settings(settings_data: CompanySettingsUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    settings = db.query(CompanySetting).filter(CompanySetting.id == "company").first()
    if not settings:
        settings = CompanySetting(id="company")
        db.add(settings)

    data = settings_data.model_dump(exclude_unset=True)

    field_mapping = {
        "name": "name",
        "logoUrl": "logo_url",
        "email": "email",
        "phone": "phone",
        "address": "address",
        "website": "website",
    }

    for api_field, db_field in field_mapping.items():
        if api_field in data:
            setattr(settings, db_field, data[api_field])

    db.commit()
    db.refresh(settings)

    return {
        "id": settings.id,
        "name": settings.name,
        "logoUrl": settings.logo_url,
        "email": settings.email,
        "phone": settings.phone,
        "address": settings.address,
        "website": settings.website,
    }


# ========== RUN SERVER ==========

if __name__ == "__main__":
    import uvicorn
    import os

    # Hosting platforms inject PORT (Render, Railway, Heroku, etc.)
    port = int(os.environ.get("PORT", 8000))
    reload = os.environ.get("ENV", "development").lower() == "development"

    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=reload)
