"""
One-time backfill for data created before materials had a purchase date,
requester and department, and before activities had sensible deadlines.

It runs automatically once on server start-up (guarded by a row in the
app_config table, so it never runs twice, even with several workers), or by
hand:

    python backfill.py            # runs if it hasn't run yet
    python backfill.py --force    # runs again (activities are re-planned)

What it does
- Materials with no purchase date get one inside their site's build period
  (never in the future).
- Materials with no requester / department get a plausible engineer and the
  department that normally orders that kind of material.
- Open (unticked, unarchived) activities get new dates relative to today:
  roughly 3 in 10 a few days overdue (red), 3 in 10 due within 48 hours
  (yellow), the rest due in 4 to 21 days. Nobody ends up weeks overdue.
Values are derived from each record's id, so the result is stable.
"""
import hashlib
import sys
from datetime import datetime, timedelta, timezone

from database import SessionLocal

BACKFILL_KEY = "backfill:materials-requesters-activity-dates:v1"

REQUESTERS = {
    "Engineering": ["Kwame Mensah", "Efua Asante", "Yaw Boateng", "Akosua Darko"],
    "Procurement": ["Abena Owusu", "Kofi Amponsah", "Esi Quaye"],
    "Operations": ["Kojo Appiah", "Adwoa Sarpong", "Nana Agyeman"],
    "Logistics": ["Kwesi Ofori", "Ama Badu"],
    "Field Services": ["Kwabena Osei", "Afia Frimpong", "Yaa Antwi"],
    "Power Systems": ["Fiifi Annan", "Selorm Agbeko"],
}

# Which department usually orders which kind of material (first match wins).
DEPARTMENT_RULES = [
    (("battery", "inverter", "solar", "generator", "rectifier", "power"), "Power Systems"),
    (("antenna", "rru", "radio", "mimo", "microwave", "dish", "router", "switch", "amplifier", "dwdm", "odf", "splice"), "Engineering"),
    (("fiber", "fibre", "cable", "pigtail", "connector", "ethernet", "duct"), "Engineering"),
    (("pole", "tower", "steel", "bracket", "concrete", "cement", "monopole", "mast", "lattice"), "Field Services"),
    (("sign", "kit", "tie", "clip", "buckle", "tensioner", "grounding", "earthing"), "Operations"),
]


def _h(*parts) -> int:
    return int(hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest(), 16)


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def department_for(name: str, seed: str) -> str:
    lowered = (name or "").lower()
    for keywords, department in DEPARTMENT_RULES:
        if any(k in lowered for k in keywords):
            return department
    return ["Procurement", "Logistics", "Operations"][_h(seed, "dept") % 3]


def backfill_materials(db, now: datetime) -> int:
    from models import Material, Site

    changed = 0
    sites = {s.id: s for s in db.query(Site).all()}
    for m in db.query(Material).all():
        touched = False
        if m.purchase_date is None:
            site = sites.get(m.site_id)
            start = _aware(site.created_at) if site and site.created_at else now - timedelta(days=90)
            start = min(start, now)
            window = max(1, min(120, (now - start).days))
            day = start + timedelta(days=_h(m.id, "date") % (window + 1))
            m.purchase_date = min(day, now).replace(hour=0, minute=0, second=0, microsecond=0)
            touched = True
        if not m.requestor_department:
            m.requestor_department = department_for(m.name, m.id)
            touched = True
        if not m.requestor:
            people = REQUESTERS.get(m.requestor_department) or REQUESTERS["Procurement"]
            m.requestor = people[_h(m.id, "who") % len(people)]
            touched = True
        changed += touched
    return changed


def replan_open_activities(db, now: datetime) -> dict:
    from models import Activity

    counts = {"overdue": 0, "due_soon": 0, "upcoming": 0}
    open_activities = (
        db.query(Activity)
        .filter(Activity.completed == False, Activity.is_archived == False)  # noqa: E712
        .all()
    )
    for a in open_activities:
        roll = _h(a.id, "state") % 10
        if roll < 3:
            end = now - timedelta(days=1 + _h(a.id, "late") % 6, hours=_h(a.id, "h") % 8)
            counts["overdue"] += 1
        elif roll < 6:
            end = now + timedelta(hours=6 + _h(a.id, "soon") % 36)
            counts["due_soon"] += 1
        else:
            end = now + timedelta(days=4 + _h(a.id, "later") % 18, hours=_h(a.id, "h") % 8)
            counts["upcoming"] += 1
        end = end.replace(minute=0, second=0, microsecond=0)
        a.end_datetime = end
        a.start_datetime = end - timedelta(days=2 + _h(a.id, "span") % 9, hours=_h(a.id, "sh") % 6)
    return counts


def run_backfill(force: bool = False) -> bool:
    """Run once. Returns True if it ran. Never raises."""
    from models import AppConfig

    db = SessionLocal()
    try:
        if not force:
            if db.get(AppConfig, BACKFILL_KEY):
                return False
            # Claim the run first so parallel workers skip it.
            db.add(AppConfig(key=BACKFILL_KEY, value="running"))
            try:
                db.commit()
            except Exception:
                db.rollback()
                return False

        now = datetime.now(timezone.utc)
        materials = backfill_materials(db, now)
        activities = replan_open_activities(db, now)
        row = db.get(AppConfig, BACKFILL_KEY)
        stamp = f"done {now.isoformat()}"
        if row:
            row.value = stamp
        else:
            db.add(AppConfig(key=BACKFILL_KEY, value=stamp))
        db.commit()
        print(f"[OK] Backfill: {materials} materials filled; open activities re-planned {activities}")
        return True
    except Exception as e:
        db.rollback()
        print(f"[WARN] Backfill failed: {type(e).__name__}: {e}")
        try:
            row = db.get(AppConfig, BACKFILL_KEY)
            if row and row.value == "running":
                db.delete(row)
                db.commit()
        except Exception:
            db.rollback()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    from database import init_db

    init_db()
    ran = run_backfill(force="--force" in sys.argv)
    if not ran:
        print("Backfill already done. Use --force to run it again.")
