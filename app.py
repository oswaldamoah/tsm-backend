from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from database import SessionLocal, Base, engine, get_db, init_db
from models import Site, Material, Activity, OperationalCost, CompanySetting
import uuid
import random
import string

# ========== INIT DB ==========
init_db()

app = FastAPI(title="Telecom Site Backend", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


class MaterialCreate(BaseModel):
    name: str
    quantity: float
    unit: str
    cost: float


class ActivityCreate(BaseModel):
    name: str
    completed: Optional[bool] = False
    activityDate: Optional[datetime] = None


class ActivityUpdate(BaseModel):
    name: Optional[str] = None
    completed: Optional[bool] = None
    activityDate: Optional[datetime] = None


class OperationalCostCreate(BaseModel):
    name: str
    amount: float


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
        "activityDate": a.activity_date.isoformat() if a.activity_date else None,
    }


def serialize_operational_cost(oc: OperationalCost) -> dict:
    return {
        "id": oc.id,
        "name": oc.name,
        "amount": oc.amount,
    }


def serialize_site(site: Site) -> dict:
    try:
        operational_costs = [serialize_operational_cost(oc) for oc in site.operational_costs]
    except Exception:
        operational_costs = []

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


# ========== SITE ROUTES ==========


@app.get("/sites")
def get_sites(
    include_archived: bool = Query(False, description="Include archived sites"),
    db: Session = Depends(get_db),
):
    try:
        query = db.query(Site)
        if not include_archived:
            query = query.filter(Site.is_archived == False)  # noqa: E712
        sites = query.all()
        return [serialize_site(site) for site in sites]
    except Exception as e:
        print(f"❌ Error in get_sites: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch sites: {str(e)}")


@app.post("/sites", status_code=201)
def create_site(site_data: SiteCreate, db: Session = Depends(get_db)):
    try:
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
def get_site(site_id: str, db: Session = Depends(get_db)):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    return serialize_site(site)


@app.put("/sites/{site_id}")
def update_site(site_id: str, site_data: SiteUpdate, db: Session = Depends(get_db)):
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
def delete_site(site_id: str, db: Session = Depends(get_db)):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    db.delete(site)
    db.commit()
    return {"message": "Site deleted"}


@app.post("/sites/{site_id}/archive")
def archive_site(site_id: str, db: Session = Depends(get_db)):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    site.is_archived = True
    db.commit()
    db.refresh(site)
    return serialize_site(site)


@app.post("/sites/{site_id}/unarchive")
def unarchive_site(site_id: str, db: Session = Depends(get_db)):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    site.is_archived = False
    db.commit()
    db.refresh(site)
    return serialize_site(site)


# ========== MATERIAL ROUTES ==========


@app.post("/sites/{site_id}/materials", status_code=201)
def add_material(site_id: str, material_data: MaterialCreate, db: Session = Depends(get_db)):
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
def delete_material(site_id: str, material_id: str, db: Session = Depends(get_db)):
    material = db.query(Material).filter(Material.id == material_id, Material.site_id == site_id).first()
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")

    db.delete(material)
    db.commit()
    return {"message": "Material deleted"}


# ========== ACTIVITY ROUTES ==========


@app.post("/sites/{site_id}/activities", status_code=201)
def add_activity(site_id: str, activity_data: ActivityCreate, db: Session = Depends(get_db)):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    new_activity = Activity(
        id=str(uuid.uuid4()),
        name=activity_data.name,
        completed=activity_data.completed or False,
        activity_date=activity_data.activityDate,
        site_id=site.id,
    )
    db.add(new_activity)
    db.commit()
    db.refresh(new_activity)
    return serialize_activity(new_activity)


@app.patch("/sites/{site_id}/activities/{activity_id}")
def update_activity(site_id: str, activity_id: str, activity_data: ActivityUpdate, db: Session = Depends(get_db)):
    activity = db.query(Activity).filter(Activity.id == activity_id, Activity.site_id == site_id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    data = activity_data.model_dump(exclude_unset=True)
    if "name" in data:
        activity.name = data["name"]
    if "completed" in data:
        activity.completed = data["completed"]
    if "activityDate" in data:
        activity.activity_date = data["activityDate"]

    db.commit()
    db.refresh(activity)
    return serialize_activity(activity)


@app.delete("/sites/{site_id}/activities/{activity_id}")
def delete_activity(site_id: str, activity_id: str, db: Session = Depends(get_db)):
    activity = db.query(Activity).filter(Activity.id == activity_id, Activity.site_id == site_id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    db.delete(activity)
    db.commit()
    return {"message": "Activity deleted"}


# ========== OPERATIONAL COST ROUTES ==========


@app.post("/sites/{site_id}/operational-costs", status_code=201)
def add_operational_cost(site_id: str, oc_data: OperationalCostCreate, db: Session = Depends(get_db)):
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
def delete_operational_cost(site_id: str, operational_cost_id: str, db: Session = Depends(get_db)):
    oc = db.query(OperationalCost).filter(OperationalCost.id == operational_cost_id, OperationalCost.site_id == site_id).first()
    if not oc:
        raise HTTPException(status_code=404, detail="Operational cost not found")

    db.delete(oc)
    db.commit()
    return {"message": "Operational cost deleted"}


# ========== COMPANY SETTINGS ROUTES ==========


@app.get("/company-settings")
def get_company_settings(db: Session = Depends(get_db)):
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
def update_company_settings(settings_data: CompanySettingsUpdate, db: Session = Depends(get_db)):
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
