"""
Read-only data tools the assistant may call.

Every tool runs a scoped SQLAlchemy query and returns plain JSON. Nothing here
writes, and no user text ever reaches the database as SQL - the model can only
pick a tool and fill in its typed arguments, so a bad or hostile question can at
worst produce an empty result set.

Each entry in TOOLS is {name, description, parameters (JSON Schema), handler}.
Handlers are called as handler(db, **arguments).
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from models import Activity, CompanySetting, Material, OperationalCost, Site


# Hard ceiling on rows returned to the model, whatever limit it asks for. Keeps
# a "list everything" question from blowing past the context window.
MAX_ROWS = 200
DEFAULT_LIMIT = 25


# ========== SHARED HELPERS ==========

def _site_costs(site: Site) -> dict:
    materials = sum(m.cost or 0.0 for m in site.materials)
    operational = sum(oc.amount or 0.0 for oc in site.operational_costs)
    labor = site.labor_cost or 0.0
    return {
        "laborCost": round(labor, 2),
        "materialsCost": round(materials, 2),
        "operationalCost": round(operational, 2),
        "totalCost": round(labor + materials + operational, 2),
    }


def _activity_progress(site: Site) -> dict:
    active = [a for a in site.activities if not a.is_archived]
    done = [a for a in active if a.completed]
    return {
        "totalActivities": len(active),
        "completedActivities": len(done),
        "percentComplete": round(len(done) / len(active) * 100, 1) if active else 0.0,
        "isComplete": bool(active) and len(done) == len(active),
    }


def _site_row(site: Site) -> dict:
    """Compact one-line view of a site - what list/aggregate tools return."""
    row = {
        "id": site.id,
        "name": site.name,
        "siteCode": site.site_code,
        "siteType": site.site_type,
        "region": site.region,
        "location": site.location,
        "isArchived": bool(site.is_archived),
        "createdAt": site.created_at.isoformat() if site.created_at else None,
    }
    row.update(_site_costs(site))
    row.update(_activity_progress(site))
    return row


def _clamp(limit: Optional[int]) -> int:
    if not limit or limit < 1:
        return DEFAULT_LIMIT
    return min(int(limit), MAX_ROWS)


def _visible_sites(db: Session, include_archived: bool) -> list[Site]:
    query = db.query(Site)
    if not include_archived:
        query = query.filter(Site.is_archived == False)  # noqa: E712
    return query.all()


def _resolve_site(db: Session, site: str) -> Optional[Site]:
    """Find a site by id, exact code, or (case-insensitive) name fragment."""
    if not site:
        return None
    needle = site.strip()
    found = db.query(Site).filter(Site.id == needle).first()
    if found:
        return found
    found = db.query(Site).filter(Site.site_code.ilike(needle)).first()
    if found:
        return found
    found = db.query(Site).filter(Site.name.ilike(needle)).first()
    if found:
        return found
    return db.query(Site).filter(Site.name.ilike(f"%{needle}%")).first()


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: Optional[datetime]) -> Optional[datetime]:
    """SQLite hands back naive datetimes; compare everything in UTC."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# ========== TOOL HANDLERS ==========

def get_overview_stats(db: Session, include_archived: bool = False) -> dict:
    """Portfolio-level totals: site counts, completion, and spend by month/year."""
    sites = _visible_sites(db, include_archived)
    archived_count = db.query(Site).filter(Site.is_archived == True).count()  # noqa: E712

    totals = {"labor": 0.0, "materials": 0.0, "operational": 0.0}
    completed_sites = 0
    monthly: dict = {}
    yearly: dict = {}

    for site in sites:
        costs = _site_costs(site)
        totals["labor"] += costs["laborCost"]
        totals["materials"] += costs["materialsCost"]
        totals["operational"] += costs["operationalCost"]

        if _activity_progress(site)["isComplete"]:
            completed_sites += 1

        created = site.created_at
        month_key = created.strftime("%Y-%m") if created else "unknown"
        year_key = created.strftime("%Y") if created else "unknown"
        for store, key in ((monthly, month_key), (yearly, year_key)):
            bucket = store.setdefault(
                key,
                {"period": key, "laborCost": 0.0, "materialsCost": 0.0,
                 "operationalCost": 0.0, "total": 0.0, "siteCount": 0},
            )
            bucket["laborCost"] += costs["laborCost"]
            bucket["materialsCost"] += costs["materialsCost"]
            bucket["operationalCost"] += costs["operationalCost"]
            bucket["total"] += costs["totalCost"]
            bucket["siteCount"] += 1

    def rows(store: dict) -> list:
        return [
            {k: (round(v, 2) if isinstance(v, float) else v) for k, v in row.items()}
            for row in sorted(store.values(), key=lambda r: r["period"])
        ]

    total_sites = len(sites)
    return {
        "currency": "GHS",
        "totalSites": total_sites,
        "archivedSites": archived_count,
        "completedSites": completed_sites,
        "completedPercentage": round(completed_sites / total_sites * 100, 1) if total_sites else 0.0,
        "totalLaborCost": round(totals["labor"], 2),
        "totalMaterialsCost": round(totals["materials"], 2),
        "totalOperationalCost": round(totals["operational"], 2),
        "totalExpenses": round(sum(totals.values()), 2),
        "monthly": rows(monthly),
        "yearly": rows(yearly),
    }


def list_sites(
    db: Session,
    name_contains: Optional[str] = None,
    region: Optional[str] = None,
    site_type: Optional[str] = None,
    status: str = "all",
    include_archived: bool = False,
    sort_by: str = "totalCost",
    descending: bool = True,
    limit: int = DEFAULT_LIMIT,
) -> dict:
    """Filtered list of sites with their costs and activity progress."""
    query = db.query(Site)
    if not include_archived:
        query = query.filter(Site.is_archived == False)  # noqa: E712
    if name_contains:
        query = query.filter(Site.name.ilike(f"%{name_contains}%"))
    if region:
        query = query.filter(Site.region.ilike(f"%{region}%"))
    if site_type:
        query = query.filter(Site.site_type.ilike(f"%{site_type}%"))

    rows = [_site_row(site) for site in query.all()]

    if status == "completed":
        rows = [r for r in rows if r["isComplete"]]
    elif status == "in_progress":
        rows = [r for r in rows if not r["isComplete"] and r["completedActivities"] > 0]
    elif status == "not_started":
        rows = [r for r in rows if r["completedActivities"] == 0]

    if rows:
        sort_key = sort_by if sort_by in rows[0] else "totalCost"
        rows.sort(key=lambda r: (r.get(sort_key) is None, r.get(sort_key)), reverse=bool(descending))

    capped = _clamp(limit)
    return {
        "currency": "GHS",
        "matchCount": len(rows),
        "returned": min(len(rows), capped),
        "sites": rows[:capped],
    }


def get_site_details(db: Session, site: str) -> dict:
    """Everything about one site: costs, materials, activities, operational costs."""
    found = _resolve_site(db, site)
    if not found:
        return {"error": f"No site matches '{site}'. Use list_sites to see available site names."}

    detail = _site_row(found)
    detail.update({
        "notes": found.notes,
        "latitude": found.latitude,
        "longitude": found.longitude,
        "materials": [
            {"name": m.name, "quantity": m.quantity, "unit": m.unit, "cost": round(m.cost or 0.0, 2)}
            for m in found.materials
        ],
        "operationalCosts": [
            {"name": oc.name, "amount": round(oc.amount or 0.0, 2)} for oc in found.operational_costs
        ],
        "activities": [
            {
                "name": a.name,
                "completed": bool(a.completed),
                "isArchived": bool(a.is_archived),
                "startDatetime": a.start_datetime.isoformat() if a.start_datetime else None,
                "endDatetime": a.end_datetime.isoformat() if a.end_datetime else None,
                "completedAt": a.completed_at.isoformat() if a.completed_at else None,
            }
            for a in found.activities
        ],
    })
    detail["currency"] = "GHS"
    return detail


def aggregate_costs(
    db: Session,
    group_by: str = "site",
    include_archived: bool = False,
    limit: int = DEFAULT_LIMIT,
    descending: bool = True,
) -> dict:
    """Spend grouped by site, region, site type, month, or year - the chart feeder."""
    sites = _visible_sites(db, include_archived)
    buckets: dict = {}

    for site in sites:
        costs = _site_costs(site)
        created = site.created_at

        if group_by == "region":
            key = site.region or "Unspecified"
        elif group_by == "site_type":
            key = site.site_type or "Unspecified"
        elif group_by == "month":
            key = created.strftime("%Y-%m") if created else "unknown"
        elif group_by == "year":
            key = created.strftime("%Y") if created else "unknown"
        else:
            key = site.name

        bucket = buckets.setdefault(
            key,
            {"group": key, "siteCount": 0, "laborCost": 0.0, "materialsCost": 0.0,
             "operationalCost": 0.0, "totalCost": 0.0},
        )
        bucket["siteCount"] += 1
        bucket["laborCost"] += costs["laborCost"]
        bucket["materialsCost"] += costs["materialsCost"]
        bucket["operationalCost"] += costs["operationalCost"]
        bucket["totalCost"] += costs["totalCost"]

    rows = [
        {k: (round(v, 2) if isinstance(v, float) else v) for k, v in bucket.items()}
        for bucket in buckets.values()
    ]

    # Time buckets read chronologically; everything else ranks by spend.
    if group_by in ("month", "year"):
        rows.sort(key=lambda r: r["group"])
    else:
        rows.sort(key=lambda r: r["totalCost"], reverse=bool(descending))

    capped = _clamp(limit)
    return {
        "currency": "GHS",
        "groupBy": group_by,
        "groupCount": len(rows),
        "groups": rows[:capped],
        "grandTotal": round(sum(r["totalCost"] for r in rows), 2),
    }


def list_activities(
    db: Session,
    site: Optional[str] = None,
    status: str = "all",
    due_before: Optional[str] = None,
    due_after: Optional[str] = None,
    include_archived: bool = False,
    limit: int = DEFAULT_LIMIT,
) -> dict:
    """Activities across sites, filterable by completion, overdue state, and dates."""
    query = db.query(Activity).join(Site, Activity.site_id == Site.id)

    if site:
        found = _resolve_site(db, site)
        if not found:
            return {"error": f"No site matches '{site}'."}
        query = query.filter(Activity.site_id == found.id)
    if not include_archived:
        query = query.filter(Activity.is_archived == False)  # noqa: E712
    if status == "completed":
        query = query.filter(Activity.completed == True)  # noqa: E712
    elif status in ("pending", "overdue"):
        query = query.filter(Activity.completed == False)  # noqa: E712

    activities = query.all()
    now = _now()
    before = _parse_date(due_before)
    after = _parse_date(due_after)

    rows = []
    for activity in activities:
        end = _as_aware(activity.end_datetime) or _as_aware(activity.activity_date)
        start = _as_aware(activity.start_datetime)
        is_overdue = bool(end and not activity.completed and end < now)

        if status == "overdue" and not is_overdue:
            continue
        if before and (not end or end > before):
            continue
        if after and (not end or end < after):
            continue

        rows.append({
            "name": activity.name,
            "site": activity.site.name if activity.site else None,
            "completed": bool(activity.completed),
            "isOverdue": is_overdue,
            "startDatetime": start.isoformat() if start else None,
            "endDatetime": end.isoformat() if end else None,
            "completedAt": _as_aware(activity.completed_at).isoformat() if activity.completed_at else None,
        })

    rows.sort(key=lambda r: (r["endDatetime"] is None, r["endDatetime"] or ""))
    capped = _clamp(limit)
    return {
        "matchCount": len(rows),
        "completedCount": sum(1 for r in rows if r["completed"]),
        "overdueCount": sum(1 for r in rows if r["isOverdue"]),
        "returned": min(len(rows), capped),
        "activities": rows[:capped],
    }


def list_materials(
    db: Session,
    site: Optional[str] = None,
    name_contains: Optional[str] = None,
    group_by_name: bool = False,
    limit: int = DEFAULT_LIMIT,
) -> dict:
    """Material line items, or spend per material name when group_by_name is true."""
    query = db.query(Material).join(Site, Material.site_id == Site.id)

    if site:
        found = _resolve_site(db, site)
        if not found:
            return {"error": f"No site matches '{site}'."}
        query = query.filter(Material.site_id == found.id)
    if name_contains:
        query = query.filter(Material.name.ilike(f"%{name_contains}%"))

    materials = query.all()
    capped = _clamp(limit)

    if group_by_name:
        buckets: dict = {}
        for material in materials:
            bucket = buckets.setdefault(
                material.name or "Unnamed",
                {"name": material.name or "Unnamed", "lineItems": 0, "totalQuantity": 0.0, "totalCost": 0.0},
            )
            bucket["lineItems"] += 1
            bucket["totalQuantity"] += material.quantity or 0.0
            bucket["totalCost"] += material.cost or 0.0
        rows = [
            {k: (round(v, 2) if isinstance(v, float) else v) for k, v in b.items()}
            for b in buckets.values()
        ]
        rows.sort(key=lambda r: r["totalCost"], reverse=True)
        return {
            "currency": "GHS",
            "groupCount": len(rows),
            "materials": rows[:capped],
            "grandTotal": round(sum(r["totalCost"] for r in rows), 2),
        }

    rows = [
        {
            "name": m.name,
            "site": m.site.name if m.site else None,
            "quantity": m.quantity,
            "unit": m.unit,
            "cost": round(m.cost or 0.0, 2),
        }
        for m in materials
    ]
    rows.sort(key=lambda r: r["cost"], reverse=True)
    return {
        "currency": "GHS",
        "matchCount": len(rows),
        "returned": min(len(rows), capped),
        "materials": rows[:capped],
        "grandTotal": round(sum(r["cost"] for r in rows), 2),
    }


def list_operational_costs(
    db: Session,
    site: Optional[str] = None,
    group_by_name: bool = False,
    limit: int = DEFAULT_LIMIT,
) -> dict:
    """Operational cost line items, optionally totalled per cost name."""
    query = db.query(OperationalCost).join(Site, OperationalCost.site_id == Site.id)
    if site:
        found = _resolve_site(db, site)
        if not found:
            return {"error": f"No site matches '{site}'."}
        query = query.filter(OperationalCost.site_id == found.id)

    costs = query.all()
    capped = _clamp(limit)

    if group_by_name:
        buckets: dict = {}
        for cost in costs:
            bucket = buckets.setdefault(cost.name or "Unnamed", {"name": cost.name or "Unnamed", "lineItems": 0, "totalAmount": 0.0})
            bucket["lineItems"] += 1
            bucket["totalAmount"] += cost.amount or 0.0
        rows = [{**b, "totalAmount": round(b["totalAmount"], 2)} for b in buckets.values()]
        rows.sort(key=lambda r: r["totalAmount"], reverse=True)
        return {"currency": "GHS", "groupCount": len(rows), "costs": rows[:capped]}

    rows = [
        {"name": c.name, "site": c.site.name if c.site else None, "amount": round(c.amount or 0.0, 2)}
        for c in costs
    ]
    rows.sort(key=lambda r: r["amount"], reverse=True)
    return {
        "currency": "GHS",
        "matchCount": len(rows),
        "returned": min(len(rows), capped),
        "costs": rows[:capped],
        "grandTotal": round(sum(r["amount"] for r in rows), 2),
    }


def get_data_dictionary(db: Session) -> dict:
    """What fields exist and which values are actually in use - orients the model."""
    regions = sorted({s.region for s in db.query(Site).all() if s.region})
    site_types = sorted({s.site_type for s in db.query(Site).all() if s.site_type})
    company = db.query(CompanySetting).filter(CompanySetting.id == "company").first()
    return {
        "currency": "GHS",
        "companyName": company.name if company else None,
        "regionsInUse": regions,
        "siteTypesInUse": site_types,
        "siteCount": db.query(Site).count(),
        "activityCount": db.query(Activity).count(),
        "materialCount": db.query(Material).count(),
        "notes": (
            "A site's total cost = laborCost + sum(material costs) + sum(operational costs). "
            "Material 'cost' is the total for that line item, not a unit price. "
            "A site counts as complete when all of its non-archived activities are completed."
        ),
    }


# ========== TOOL SCHEMAS ==========

_LIMIT_SCHEMA = {
    "type": "integer",
    "description": f"Max rows to return (default {DEFAULT_LIMIT}, hard cap {MAX_ROWS}).",
}

DATA_TOOLS: list[dict] = [
    {
        "name": "get_data_dictionary",
        "description": (
            "Describes the dataset: company name, which regions and site types actually exist, "
            "record counts, and how costs are calculated. Call this first when unsure what the data contains."
        ),
        "parameters": {"type": "object", "properties": {}},
        "handler": get_data_dictionary,
    },
    {
        "name": "get_overview_stats",
        "description": (
            "Portfolio totals: number of sites, how many are complete, total labor/materials/operational "
            "spend, and spend broken down by month and by year. Use for 'how are we doing overall' questions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "include_archived": {
                    "type": "boolean",
                    "description": "Include archived sites in the totals (default false).",
                }
            },
        },
        "handler": get_overview_stats,
    },
    {
        "name": "list_sites",
        "description": (
            "List sites with cost and activity-progress figures, filtered by name, region, site type, "
            "or completion status. Use for 'which sites...' and 'top N sites by cost' questions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name_contains": {"type": "string", "description": "Case-insensitive fragment of the site name."},
                "region": {"type": "string", "description": "Region filter (partial match allowed)."},
                "site_type": {"type": "string", "description": "Site type filter, e.g. 4G, 5G, Fiber."},
                "status": {
                    "type": "string",
                    "enum": ["all", "completed", "in_progress", "not_started"],
                    "description": "Completion status based on the site's activities.",
                },
                "include_archived": {"type": "boolean"},
                "sort_by": {
                    "type": "string",
                    "enum": ["totalCost", "laborCost", "materialsCost", "operationalCost",
                             "percentComplete", "name", "createdAt"],
                },
                "descending": {"type": "boolean"},
                "limit": _LIMIT_SCHEMA,
            },
        },
        "handler": list_sites,
    },
    {
        "name": "get_site_details",
        "description": (
            "Full detail for one site: every material, activity and operational cost, plus totals "
            "and location. Accepts a site name, site code, or id."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "site": {"type": "string", "description": "Site name, site code, or id."}
            },
            "required": ["site"],
        },
        "handler": get_site_details,
    },
    {
        "name": "aggregate_costs",
        "description": (
            "Spend grouped by site, region, site type, month, or year, with labor/materials/operational "
            "split out. This is the tool to call before drawing a cost chart."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "group_by": {
                    "type": "string",
                    "enum": ["site", "region", "site_type", "month", "year"],
                },
                "include_archived": {"type": "boolean"},
                "descending": {"type": "boolean"},
                "limit": _LIMIT_SCHEMA,
            },
            "required": ["group_by"],
        },
        "handler": aggregate_costs,
    },
    {
        "name": "list_activities",
        "description": (
            "Activities across all sites or one site, filtered by completion status, overdue state, "
            "or due-date window. Use for scheduling, progress and overdue-work questions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "site": {"type": "string", "description": "Restrict to one site (name, code, or id)."},
                "status": {
                    "type": "string",
                    "enum": ["all", "completed", "pending", "overdue"],
                    "description": "'overdue' means not completed and past its end date.",
                },
                "due_before": {"type": "string", "description": "ISO date; keep activities ending on or before this."},
                "due_after": {"type": "string", "description": "ISO date; keep activities ending on or after this."},
                "include_archived": {"type": "boolean"},
                "limit": _LIMIT_SCHEMA,
            },
        },
        "handler": list_activities,
    },
    {
        "name": "list_materials",
        "description": (
            "Material line items, optionally for one site. Set group_by_name to total spend per "
            "material across the portfolio - useful for 'what are we spending most on' questions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "site": {"type": "string"},
                "name_contains": {"type": "string"},
                "group_by_name": {"type": "boolean"},
                "limit": _LIMIT_SCHEMA,
            },
        },
        "handler": list_materials,
    },
    {
        "name": "list_operational_costs",
        "description": (
            "Operational cost line items, optionally for one site, or totalled per cost name "
            "when group_by_name is true."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "site": {"type": "string"},
                "group_by_name": {"type": "boolean"},
                "limit": _LIMIT_SCHEMA,
            },
        },
        "handler": list_operational_costs,
    },
]


DATA_TOOLS_BY_NAME = {tool["name"]: tool for tool in DATA_TOOLS}
