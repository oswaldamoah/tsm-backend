"""
Seed script to populate the telecom site database with realistic Ghana-based data.

Run with: python seed_data.py

This script adds 6 diverse telecom sites across Ghana covering:
- Various regions (Ashanti, Western, Northern, Central, Eastern, Upper East, Greater Accra)
- Different site types (5G, Fiber, 4G, Microwave, 2G Legacy)
- Different lifecycle stages (planning, under construction, operational, archived)
- Full nested data: materials, activities, operational costs, notes, stock images
"""

import json
import uuid
from datetime import datetime, timezone, timedelta

from database import SessionLocal, init_db
from models import Site, Material, Activity, OperationalCost

# ========== HELPER ==========

def make_material(name, quantity, unit, cost):
    return Material(
        id=str(uuid.uuid4()),
        name=name,
        quantity=quantity,
        unit=unit,
        cost=cost,
    )


def make_activity(name, completed, activity_date=None, completed_at=None):
    return Activity(
        id=str(uuid.uuid4()),
        name=name,
        completed=completed,
        activity_date=activity_date,
        completed_at=completed_at if completed else None,
    )


def make_operational_cost(name, amount):
    return OperationalCost(
        id=str(uuid.uuid4()),
        name=name,
        amount=amount,
    )


# ========== SITE DATA ==========

sites_data = [
    # ─────────────────────────────────────────────────────────────
    # 1. Kumasi Adum 5G Tower — 5G rollout, fully operational
    # ─────────────────────────────────────────────────────────────
    {
        "name": "Kumasi Adum 5G Tower",
        "site_code": "TEL-KMAS-5G01",
        "site_type": "5G",
        "region": "Ashanti",
        "location": "Adum, Kumasi",
        "latitude": 6.6851,
        "longitude": -1.6218,
        "google_maps_url": "https://maps.google.com/?q=6.6851,-1.6218",
        "images": json.dumps([
            "https://images.unsplash.com/photo-1516387938699-a93567ec168e?w=600&q=80",
            "https://images.unsplash.com/photo-1518770660439-4636190af475?w=600&q=80",
            "https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=600&q=80",
        ]),
        "notes": "Flagship 5G site in the heart of Kumasi business district. Active 5G NR on n78 (3.5GHz) and DSS on n1. Backup power: 2x 48V lithium battery banks + 30kVA generator. Housing agreement with Adum Plaza management. 24/7 security guard on site. Access via Prempeh II Street off the Adum Roundabout — gate code 4821.",
        "is_archived": False,
        "labor_cost": 18500.0,
        "created_at": datetime(2025, 8, 15, 9, 30),
        "updated_at": datetime(2026, 6, 10, 10, 0),
        "materials": [
            make_material("5G Massive MIMO Antenna (64T64R)", 3, "pcs", 42500.0),
            make_material("RRU 5G (n78)", 3, "pcs", 18500.0),
            make_material("Fiber Optic Cable (Armored, 48-core)", 850, "m", 85.0),
            make_material("48V Lithium Battery Bank (200Ah)", 2, "banks", 32000.0),
            make_material("3-Phase Inverter", 1, "pcs", 14500.0),
            make_material("EMF Warning Signs", 4, "pcs", 150.0),
            make_material("Grounding Kit Complete", 1, "set", 3800.0),
        ],
        "activities": [
            make_activity("Site Survey & RF Planning", True, datetime(2026, 1, 10, 9, 0), datetime(2026, 1, 10, 16, 30)),
            make_activity("Civil Works — Concrete Pad & Fencing", True, datetime(2026, 2, 1, 8, 0), datetime(2026, 2, 5, 17, 0)),
            make_activity("Tower Erection (35m Lattice)", True, datetime(2026, 3, 5, 8, 0), datetime(2026, 3, 12, 16, 0)),
            make_activity("5G Equipment Installation", True, datetime(2026, 4, 12, 9, 0), datetime(2026, 4, 18, 14, 0)),
            make_activity("Fiber Backhaul Splicing", True, datetime(2026, 4, 20, 9, 0)),
            make_activity("Commissioning & Drive Test", True, datetime(2026, 5, 15, 10, 0)),
            make_activity("Live Traffic Cutover", True, datetime(2026, 6, 1, 23, 0)),
            make_activity("Client Handover", True, datetime(2026, 6, 10, 10, 0)),
            make_activity("Quarterly Preventive Maintenance", False, datetime(2026, 9, 5, 8, 0)),
        ],
        "operational_costs": [
            make_operational_cost("Site Rent (Adum Plaza)", 4500.0),
            make_operational_cost("Generator Fuel (Monthly Avg)", 2200.0),
            make_operational_cost("Security Guard Service", 1800.0),
            make_operational_cost("Backhaul Fiber Lease", 3500.0),
            make_operational_cost("Site Maintenance Contract", 2800.0),
        ],
    },
    # ─────────────────────────────────────────────────────────────
    # 2. Takoradi Harbour Fiber Node — Fiber site for port connectivity
    # ─────────────────────────────────────────────────────────────
    {
        "name": "Takoradi Harbour Fiber Node",
        "site_code": "TEL-TAKR-FB07",
        "site_type": "Fiber",
        "region": "Western",
        "location": "Takoradi Harbour, Sekondi-Takoradi",
        "latitude": 4.8845,
        "longitude": -1.7554,
        "google_maps_url": "https://maps.google.com/?q=4.8845,-1.7554",
        "images": json.dumps([
            "https://images.unsplash.com/photo-1516387938699-a93567ec168e?w=600&q=80",
            "https://images.unsplash.com/photo-1461749280684-dccba630e2f6?w=600&q=80",
        ]),
        "notes": "Fiber aggregation node serving the Takoradi Harbour expansion zone. Provides high-capacity backhaul for maritime logistics and port operation systems. 288-core distribution hub with DWDM transport. Dual redundant power feeds from harbour grid. Flood mitigation installed after 2025 rains. Access requires harbour security clearance — contact Port Authority escort desk.",
        "is_archived": False,
        "labor_cost": 9800.0,
        "created_at": datetime(2025, 8, 25, 10, 15),
        "updated_at": datetime(2026, 2, 20, 14, 0),
        "materials": [
            make_material("Fiber Distribution Hub (288-core)", 1, "pcs", 68000.0),
            make_material("DWDM Mux/Demux Module", 4, "pcs", 12500.0),
            make_material("Fiber Patch Cables (LC-LC)", 120, "pcs", 45.0),
            make_material("Fusion Splicer Consumables", 1, "set", 2500.0),
            make_material("Equipment Rack (42U)", 2, "racks", 5200.0),
            make_material("Redundant Power Supply Unit", 2, "pcs", 6800.0),
        ],
        "activities": [
            make_activity("Harbour Site Feasibility Study", True, datetime(2025, 9, 15, 9, 0), datetime(2025, 9, 15, 17, 0)),
            make_activity("Duct & Cable Trench Excavation", True, datetime(2025, 10, 20, 8, 0), datetime(2025, 11, 5, 16, 0)),
            make_activity("Fiber Cable Installation (12km)", True, datetime(2025, 11, 10, 8, 0), datetime(2025, 11, 28, 15, 0)),
            make_activity("Node Cabinet Installation", True, datetime(2025, 12, 5, 9, 0), datetime(2025, 12, 8, 17, 0)),
            make_activity("DWDM System Commissioning", True, datetime(2026, 1, 18, 10, 0), datetime(2026, 1, 22, 14, 0)),
            make_activity("Port Authority Integration Testing", True, datetime(2026, 2, 2, 9, 0), datetime(2026, 2, 10, 13, 0)),
            make_activity("Go-Live", True, datetime(2026, 2, 20, 11, 0), datetime(2026, 2, 20, 14, 0)),
        ],
        "operational_costs": [
            make_operational_cost("Harbour Authority Right-of-Way Fee", 8500.0),
            make_operational_cost("Power (Grid + UPS)", 3200.0),
            make_operational_cost("Monthly Fiber Audit", 1500.0),
            make_operational_cost("Equipment Cooling", 1900.0),
        ],
    },
    # ─────────────────────────────────────────────────────────────
    # 3. Tamale Central 4G Site — rural/urban coverage expansion
    # ─────────────────────────────────────────────────────────────
    {
        "name": "Tamale Central 4G Tower",
        "site_code": "TEL-TAML-4G22",
        "site_type": "4G",
        "region": "Northern",
        "location": "Tamale Central, near Jubilee Park",
        "latitude": 9.4075,
        "longitude": -0.8533,
        "google_maps_url": "https://maps.google.com/?q=9.4075,-0.8533",
        "images": json.dumps([
            "https://images.unsplash.com/photo-1519283144143-570e4bb2a067?w=600&q=80",
            "https://images.unsplash.com/photo-1518770660439-4636190af475?w=600&q=80",
        ]),
        "notes": "New 4G LTE site improving mobile broadband in Tamale metropolis. 2-sector configuration on 35m monopole (B3 1800MHz + B28 700MHz for wide rural coverage). Solar-assisted hybrid power to reduce grid dependence — 18 panels + 4 battery banks. Site compound shared with two other operators. Key corridor site for Tamale–Walewale highway coverage. Site caretaker: Alhaji Issah (0244 123 456).",
        "is_archived": False,
        "labor_cost": 7600.0,
        "created_at": datetime(2025, 10, 20, 8, 45),
        "updated_at": datetime(2026, 4, 12, 10, 10),
        "materials": [
            make_material("35m Monopole Tower", 1, "pcs", 54500.0),
            make_material("4G LTE RRU (B3/B28)", 2, "pcs", 9800.0),
            make_material("Panel Antenna (Dual-band)", 2, "pcs", 3200.0),
            make_material("Solar Panels (450W)", 18, "pcs", 950.0),
            make_material("Lithium Battery Bank (48V 100Ah)", 4, "banks", 18500.0),
            make_material("Hybrid Charge Controller", 2, "pcs", 4200.0),
            make_material("Chain Link Fence (Complete)", 1, "set", 8500.0),
            make_material("Earthing & Lightning Protection", 1, "set", 4800.0),
        ],
        "activities": [
            make_activity("Community Consultation & Land Agreement", True, datetime(2025, 11, 5, 9, 0), datetime(2025, 11, 5, 15, 30)),
            make_activity("Soil Test & Civil Foundation Works", True, datetime(2025, 12, 8, 8, 0), datetime(2025, 12, 15, 16, 0)),
            make_activity("Monopole Installation", True, datetime(2026, 1, 20, 8, 30), datetime(2026, 1, 24, 17, 0)),
            make_activity("Solar Power System Installation", True, datetime(2026, 2, 10, 9, 0), datetime(2026, 2, 14, 15, 0)),
            make_activity("LTE Equipment Install & Commission", True, datetime(2026, 3, 5, 9, 0), datetime(2026, 3, 10, 14, 30)),
            make_activity("RF Optimization & Drive Test", True, datetime(2026, 3, 25, 10, 0), datetime(2026, 3, 28, 16, 0)),
            make_activity("Launch & Community Sensitization", True, datetime(2026, 4, 10, 9, 0), datetime(2026, 4, 10, 13, 0)),
            make_activity("Solar Panel Cleaning Rota Setup", False, datetime(2026, 8, 1, 8, 0)),
        ],
        "operational_costs": [
            make_operational_cost("Land Lease (Tamale Central)", 2200.0),
            make_operational_cost("Hybrid Power Maintenance", 1600.0),
            make_operational_cost("Site Caretaker Allowance", 700.0),
            make_operational_cost("Microwave Link Lease", 2400.0),
        ],
    },
    # ─────────────────────────────────────────────────────────────
    # 4. UCC Cape Coast Campus Mast — university campus coverage
    # ─────────────────────────────────────────────────────────────
    {
        "name": "UCC Cape Coast Campus Mast",
        "site_code": "TEL-UCC-4G15",
        "site_type": "4G",
        "region": "Central",
        "location": "University of Cape Coast, near Science Complex",
        "latitude": 5.1202,
        "longitude": -1.2851,
        "google_maps_url": "https://maps.google.com/?q=5.1202,-1.2851",
        "images": json.dumps([
            "https://images.unsplash.com/photo-1516387938699-a93567ec168e?w=600&q=80",
            "https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=600&q=80",
            "https://images.unsplash.com/photo-1431540015161-0bf868a2d407?w=600&q=80",
        ]),
        "notes": "Campus-wide capacity site for University of Cape Coast supporting 18,000+ students. Strategic site for e-learning and digital library programs. High-capacity 4G LTE-A (2x20MHz CA) with indoor DAS extension into Science Complex and library. Co-located with university ICT directorate. Exam period priority — network ops to monitor bandwidth during May/June exams. University contact: ICT Director, Prof. K. Mensah.",
        "is_archived": False,
        "labor_cost": 12500.0,
        "created_at": datetime(2025, 12, 1, 9, 45),
        "updated_at": datetime(2026, 4, 9, 14, 0),
        "materials": [
            make_material("LTE-A RRU (Carrier Aggregation)", 3, "pcs", 11200.0),
            make_material("Dual-band Panel Antenna", 3, "pcs", 3400.0),
            make_material("Indoor DAS Repeater Units", 8, "pcs", 5200.0),
            make_material("Backhaul Microwave Dish (23GHz)", 1, "pcs", 18500.0),
            make_material("Fiber Conversion Cabinet", 1, "pcs", 17500.0),
            make_material("Safety Barriers & Cones", 12, "pcs", 120.0),
            make_material("Equipment AC Unit (3kW)", 2, "pcs", 6800.0),
        ],
        "activities": [
            make_activity("University Agreement & Access Permits", True, datetime(2026, 1, 12, 9, 0), datetime(2026, 1, 16, 14, 0)),
            make_activity("Roof-mount Survey (Science Complex)", True, datetime(2026, 2, 2, 9, 0), datetime(2026, 2, 2, 13, 30)),
            make_activity("Microwave Backhaul Install", True, datetime(2026, 2, 25, 8, 30), datetime(2026, 3, 1, 16, 0)),
            make_activity("Main Antenna Array Installation", True, datetime(2026, 3, 8, 9, 0), datetime(2026, 3, 12, 15, 30)),
            make_activity("Indoor DAS Deployment", True, datetime(2026, 3, 20, 9, 0), datetime(2026, 3, 27, 17, 0)),
            make_activity("Integration & Optimization", True, datetime(2026, 4, 5, 10, 0), datetime(2026, 4, 9, 14, 0)),
            make_activity("Campus-wide Drive Test & Warm-up", False, datetime(2026, 9, 15, 10, 0)),
        ],
        "operational_costs": [
            make_operational_cost("UCC Facility Rental Agreement", 3800.0),
            make_operational_cost("University Electricity Supply", 2100.0),
            make_operational_cost("Microwave Link Lease", 2600.0),
            make_operational_cost("Annual Access/Insurance", 900.0),
        ],
    },
    # ─────────────────────────────────────────────────────────────
    # 5. Akosombo Dam Microwave Relay — under construction
    # ─────────────────────────────────────────────────────────────
    {
        "name": "Akosombo Dam Microwave Relay",
        "site_code": "TEL-AKOS-MW03",
        "site_type": "Microwave",
        "region": "Eastern",
        "location": "Akosombo, VRA Dam Catchment Area",
        "latitude": 6.2738,
        "longitude": 0.0601,
        "google_maps_url": "https://maps.google.com/?q=6.2738,0.0601",
        "images": json.dumps([
            "https://images.unsplash.com/photo-1519283144143-570e4bb2a067?w=600&q=80",
            "https://images.unsplash.com/photo-1431540015161-0bf868a2d407?w=600&q=80",
        ]),
        "notes": "Critical microwave relay hop connecting Volta Region corridor. Provides resilient backhaul path independent of terrestrial fiber (survives fiber cuts on Accra–Ho route). 11GHz link to Kpong and 15GHz hop toward Ho. Currently under construction — tower base complete, antenna installation scheduled. VRA access permit required for all site visits. Height: 40m self-supporting tower. ETA for link ready: Q4 2026.",
        "is_archived": False,
        "labor_cost": 6400.0,
        "created_at": datetime(2026, 2, 1, 8, 30),
        "updated_at": datetime(2026, 6, 22, 17, 0),
        "materials": [
            make_material("40m Self-supporting Tower", 1, "pcs", 78500.0),
            make_material("Microwave Dish Antenna (11GHz, 1.8m)", 2, "pcs", 14800.0),
            make_material("Microwave Radio Unit (11GHz)", 2, "pcs", 22500.0),
            make_material("Splitter/Combiner Assembly", 2, "pcs", 4500.0),
            make_material("Tower Lightning Rod & Down Conductor", 1, "set", 3900.0),
            make_material("Concrete Foundation Kit", 1, "set", 12500.0),
            make_material("Steel Mounting Brackets (Heavy Duty)", 8, "pcs", 680.0),
        ],
        "activities": [
            make_activity("VRA Land & Access Approval", True, datetime(2026, 3, 2, 9, 0), datetime(2026, 3, 6, 11, 0)),
            make_activity("Topographical & Line-of-Sight Survey", True, datetime(2026, 4, 6, 8, 0), datetime(2026, 4, 8, 15, 0)),
            make_activity("Foundation Excavation & Pouring", True, datetime(2026, 5, 10, 7, 0), datetime(2026, 5, 18, 16, 30)),
            make_activity("Tower Erection (40m)", True, datetime(2026, 6, 15, 8, 0), datetime(2026, 6, 22, 17, 0)),
            make_activity("Microwave Dish Installation", False, datetime(2026, 8, 20, 9, 0)),
            make_activity("Link Alignment & Testing", False, datetime(2026, 9, 5, 10, 0)),
            make_activity("Integration into Network", False, datetime(2026, 9, 25, 10, 0)),
        ],
        "operational_costs": [
            make_operational_cost("VRA Land Lease", 1800.0),
            make_operational_cost("Security (VRA Joint Patrol)", 1200.0),
            make_operational_cost("Construction Power (Temporary)", 650.0),
            make_operational_cost("Transport & Logistics (Marine access)", 2400.0),
        ],
    },
    # ─────────────────────────────────────────────────────────────
    # 6. Old Nungua Legacy Site — ARCHIVED / decommissioned
    # ─────────────────────────────────────────────────────────────
    {
        "name": "Old Nungua Legacy Site",
        "site_code": "TEL-NGUA-2G99",
        "site_type": "2G",
        "region": "Greater Accra",
        "location": "Old Nungua, near Teshie-Nungua road",
        "latitude": 5.6196,
        "longitude": -0.0693,
        "google_maps_url": "https://maps.google.com/?q=5.6196,-0.0693",
        "images": json.dumps([
            "https://images.unsplash.com/photo-1516387938699-a93567ec168e?w=600&q=80",
        ]),
        "notes": "Legacy 2G GSM site decommissioned March 2026 and replaced by the newer Nungua Barrier site. Equipment removed — only the 25m tower remains pending salvage. Pending tasks: tower dismantling permit from municipal assembly, final HSE inspection, and site lease termination notice (3 months). Archived to remove from active site management view. Contact: Municipal Works Dept for dismantling permits.",
        "is_archived": True,
        "labor_cost": 0.0,
        "created_at": datetime(2015, 6, 10, 9, 0),
        "updated_at": datetime(2026, 3, 12, 12, 0),
        "materials": [
            make_material("Salvaged Copper Ground Cables", 25, "kg", 0.0),
            make_material("Scrap Steel (Tower Sections)", 380, "kg", 0.0),
        ],
        "activities": [
            make_activity("Equipment De-inventory", True, datetime(2026, 2, 15, 9, 0), datetime(2026, 2, 15, 16, 0)),
            make_activity("RF Equipment Removal", True, datetime(2026, 3, 2, 8, 0), datetime(2026, 3, 4, 14, 0)),
            make_activity("Site Cleanup & Hazard Assessment", True, datetime(2026, 3, 10, 8, 0), datetime(2026, 3, 12, 12, 0)),
            make_activity("Tower Dismantling Permit Application", False, None),
            make_activity("Final Site Handback to Landlord", False, None),
        ],
        "operational_costs": [
            make_operational_cost("Lease Termination Penalty", 4500.0),
            make_operational_cost("Site Restoration / Green Works", 6800.0),
        ],
    },
    # ─────────────────────────────────────────────────────────────
    # 7. Bolgatanga Rural Connectivity Tower — in planning phase
    # ─────────────────────────────────────────────────────────────
    {
        "name": "Bolgatanga Rural Connectivity Tower",
        "site_code": "TEL-BOLG-RU42",
        "site_type": "4G",
        "region": "Upper East",
        "location": "Bolgatanga–Zuarungu road, rural catchment",
        "latitude": 10.7791,
        "longitude": -0.8512,
        "google_maps_url": "https://maps.google.com/?q=10.7791,-0.8512",
        "images": json.dumps([
            "https://images.unsplash.com/photo-1516387938699-a93567ec168e?w=600&q=80",
            "https://images.unsplash.com/photo-1446776811953-b23d57bd21aa?w=600&q=80",
        ]),
        "notes": "Rural connectivity initiative site under the national universal access program (GIFEC partnership). Will extend LTE coverage to ~15 surrounding farming communities. Design: off-grid solar + battery (100% renewable, no grid dependency). Forthcoming activities: community land negotiation with Zuarungu chief, environmental assessment, frequency license for low-band 700MHz. Currently in planning — no construction started. Funding: Universal Service Fund (USF).",
        "is_archived": False,
        "labor_cost": 0.0,
        "created_at": datetime(2026, 7, 5, 10, 0),
        "updated_at": datetime(2026, 7, 20, 11, 30),
        "materials": [
            make_material("Planned: Solar Panel Array (450W)", 24, "pcs", 950.0),
            make_material("Planned: 30m Lattice Tower", 1, "pcs", 46500.0),
            make_material("Planned: LTE Low-band RRU (B28)", 2, "pcs", 10200.0),
            make_material("Planned: Solar Battery Bank (48V 200Ah)", 5, "banks", 19500.0),
        ],
        "activities": [
            make_activity("Community Land Negotiation with Chief", False, datetime(2026, 9, 15, 9, 0)),
            make_activity("GIFEC Funding Approval", False, datetime(2026, 10, 1, 9, 0)),
            make_activity("Environmental Impact Assessment", False, None),
            make_activity("Civil Works & Tower Erection", False, None),
            make_activity("Solar / Off-grid Installation", False, None),
            make_activity("Launch & Community Handover", False, None),
        ],
        "operational_costs": [
            make_operational_cost("Community Land Lease (Under Negotiation)", 500.0),
            make_operational_cost("GIS / Survey Consultant Fee", 2500.0),
        ],
    },
]

# ========== SEED FUNCTION ==========

def seed():
    init_db()
    db = SessionLocal()
    added = 0
    skipped = 0

    for data in sites_data:
        # Skip if a site with this code already exists
        existing = db.query(Site).filter(Site.site_code == data["site_code"]).first()
        if existing:
            print(f"⏭️  Skipping {data['name']} — site_code {data['site_code']} already exists")
            skipped += 1
            continue

        materials = data.pop("materials", [])
        activities = data.pop("activities", [])
        operational_costs = data.pop("operational_costs", [])

        site = Site(
            id=str(uuid.uuid4()),
            **data,
        )
        site.materials = materials
        site.activities = activities
        site.operational_costs = operational_costs

        db.add(site)
        db.flush()

        mat_cost = sum(m.cost * m.quantity for m in materials)
        act_done = sum(1 for a in activities if a.completed)
        act_total = len(activities)
        oc_total = sum(o.amount for o in operational_costs)

        print(f"✅ Added: {data['name']}")
        print(f"   Code: {data['site_code']} | Type: {data['site_type']} | Region: {data['region']}")
        print(f"   Materials: {len(materials)} | Activities: {act_done}/{act_total} done | OpCosts: {len(operational_costs)}")
        print(f"   Materials Cost: GHS {mat_cost:,.2f} | Labor: GHS {data['labor_cost']:,.2f} | OpCosts: GHS {oc_total:,.2f}")
        print(f"   Archived: {data['is_archived']}")
        print()

        added += 1

    db.commit()
    db.close()

    total = added + skipped
    print(f"{'='*60}")
    print(f"Done! Added {added} new site(s) | Skipped {skipped} existing | Total processed: {total}")
    print(f"Run 'python -c \"from database import SessionLocal; from models import Site; db = SessionLocal(); print(len(db.query(Site).all()), 'sites total')\"' to verify.")


if __name__ == "__main__":
    seed()