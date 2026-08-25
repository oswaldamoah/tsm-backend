from database import SessionLocal
from models import Site, Activity
from datetime import datetime, timezone

db = SessionLocal()

# Update sites with created_at/updated_at
site_updates = {
    'TEL-KMAS-5G01': (datetime(2025, 8, 15, 9, 30), datetime(2026, 6, 10, 10, 0)),
    'TEL-TAKR-FB07': (datetime(2025, 8, 25, 10, 15), datetime(2026, 2, 20, 14, 0)),
    'TEL-TAML-4G22': (datetime(2025, 10, 20, 8, 45), datetime(2026, 4, 12, 10, 10)),
    'TEL-UCC-4G15': (datetime(2025, 12, 1, 9, 45), datetime(2026, 4, 9, 14, 0)),
    'TEL-AKOS-MW03': (datetime(2026, 2, 1, 8, 30), datetime(2026, 6, 22, 17, 0)),
    'TEL-NGUA-2G99': (datetime(2015, 6, 10, 9, 0), datetime(2026, 3, 12, 12, 0)),
    'TEL-BOLG-RU42': (datetime(2026, 7, 5, 10, 0), datetime(2026, 7, 20, 11, 30)),
}

for code, (created, updated) in site_updates.items():
    site = db.query(Site).filter(Site.site_code == code).first()
    if site:
        site.created_at = created
        site.updated_at = updated
        print(f'Updated site {code}')

# Update activities with completed_at
activity_updates = {
    'Site Survey & RF Planning': datetime(2026, 1, 10, 16, 30),
    'Civil Works — Concrete Pad & Fencing': datetime(2026, 2, 5, 17, 0),
    'Tower Erection (35m Lattice)': datetime(2026, 3, 12, 16, 0),
    '5G Equipment Installation': datetime(2026, 4, 18, 14, 0),
    'Harbour Site Feasibility Study': datetime(2025, 9, 15, 17, 0),
    'Duct & Cable Trench Excavation': datetime(2025, 11, 5, 16, 0),
    'Fiber Cable Installation (12km)': datetime(2025, 11, 28, 15, 0),
    'Node Cabinet Installation': datetime(2025, 12, 8, 17, 0),
    'DWDM System Commissioning': datetime(2026, 1, 22, 14, 0),
    'Port Authority Integration Testing': datetime(2026, 2, 10, 13, 0),
    'Go-Live': datetime(2026, 2, 20, 14, 0),
    'Community Consultation & Land Agreement': datetime(2025, 11, 5, 15, 30),
    'Soil Test & Civil Foundation Works': datetime(2025, 12, 15, 16, 0),
    'Monopole Installation': datetime(2026, 1, 24, 17, 0),
    'Solar Power System Installation': datetime(2026, 2, 14, 15, 0),
    'LTE Equipment Install & Commission': datetime(2026, 3, 10, 14, 30),
    'RF Optimization & Drive Test': datetime(2026, 3, 28, 16, 0),
    'Launch & Community Sensitization': datetime(2026, 4, 10, 13, 0),
    'University Agreement & Access Permits': datetime(2026, 1, 16, 14, 0),
    'Roof-mount Survey (Science Complex)': datetime(2026, 2, 2, 13, 30),
    'Microwave Backhaul Install': datetime(2026, 3, 1, 16, 0),
    'Main Antenna Array Installation': datetime(2026, 3, 12, 15, 30),
    'Indoor DAS Deployment': datetime(2026, 3, 27, 17, 0),
    'Integration & Optimization': datetime(2026, 4, 9, 14, 0),
    'VRA Land & Access Approval': datetime(2026, 3, 6, 11, 0),
    'Topographical & Line-of-Sight Survey': datetime(2026, 4, 8, 15, 0),
    'Foundation Excavation & Pouring': datetime(2026, 5, 18, 16, 30),
    'Tower Erection (40m)': datetime(2026, 6, 22, 17, 0),
    'Equipment De-inventory': datetime(2026, 2, 15, 16, 0),
    'RF Equipment Removal': datetime(2026, 3, 4, 14, 0),
    'Site Cleanup & Hazard Assessment': datetime(2026, 3, 12, 12, 0),
}

for name, completed_at in activity_updates.items():
    act = db.query(Activity).filter(Activity.name == name).first()
    if act and act.completed:
        act.completed_at = completed_at
        print(f'Updated activity: {name}')

db.commit()
print('Done!')