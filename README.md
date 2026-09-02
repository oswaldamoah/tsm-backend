# Telecom Site Backend

FastAPI + PostgreSQL (Neon) REST API for managing telecom sites — materials, scrum-style activities (with sprint start/end dates and bulk archiving), operational costs, company settings, site stats/expense reporting, and full JSON import/export. Ready to deploy and connect straight to your frontend.

---

## ✅ Hosting Readiness Checklist

| Item | Status |
|------|--------|
| CORS enabled for all origins | ✅ `allow_origins=["*"]` |
| Cloud PostgreSQL (Neon) in `.env` | ✅ `DATABASE_URL` set |
| Auto table creation + migrations on startup | ✅ `init_db()` runs automatically |
| `PORT` env var supported (Render/Railway/Heroku) | ✅ |
| Gunicorn + Uvicorn workers for production | ✅ `Procfile` included |
| Auto-reload disabled in production | ✅ `reload` only when `ENV=development` |

---

## 🚀 Deploying (3 options)

Pick one. No local install needed.

### Option A — Render (free tier, fastest)

1. Push this repo to GitHub.
2. On [render.com](https://render.com): **New → Web Service** → connect your repo.
3. Fill in:
   | Field | Value |
   |-------|-------|
   | **Build Command** | `pip install -r requirements.txt` |
   | **Start Command** | `gunicorn app:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT` |
   | **Environment** | Add `DATABASE_URL` (already in your `.env`) |
4. **Deploy**. Done. You'll get a URL like `https://your-app.onrender.com`.

### Option B — Railway

1. Push repo to GitHub → [railway.app](https://railway.app) → **New Project → Deploy from GitHub**.
2. Railway auto-detects the `Procfile` and installs from `requirements.txt`.
3. Add the `DATABASE_URL` variable under **Variables**.
4. Railway assigns a public URL automatically.

### Option C — Heroku

```bash
heroku create your-app-name
heroku config:set DATABASE_URL="postgresql://..." 
heroku config:set ENV=production
git push heroku main
```

---

## 🔌 Connecting Your Frontend

Your frontend just needs the **base URL** of this API:

```
https://your-app.onrender.com
```

**Important files your frontend needs:**

| File | Purpose |
|------|---------|
| `.env` at the repo root | Holds `DATABASE_URL` (Neon PostgreSQL) |
| `Procfile` | Tells the host how to run the app (Gunicorn/Uvicorn) |
| `requirements.txt` | Python dependencies for the host |
| `database.py` | Reads `DATABASE_URL`, auto-creates tables & migrations |

### Example `fetch` call

```js
const API_BASE = "https://your-app.onrender.com"; // ← your deployed URL

// GET all sites
const sites = await fetch(`${API_BASE}/sites`).then(res => res.json());

// GET a single site
const site = await fetch(`${API_BASE}/sites/${siteId}`).then(res => res.json());

// POST a new site
const newSite = await fetch(`${API_BASE}/sites`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ name: "Accra Tower 7" }),
}).then(res => res.json());

// PUT update a site
await fetch(`${API_BASE}/sites/${siteId}`, {
  method: "PUT",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ region: "Greater Accra" }),
});

// DELETE a site
await fetch(`${API_BASE}/sites/${siteId}`, { method: "DELETE" });
```

> 💡 **CORS is wide open** (`allow_origins=["*"]`), so your frontend can be hosted anywhere — Vercel, Netlify, GitHub Pages, an Electron app, anything.

---

## 📚 API Reference

Base URL: `https://your-app.onrender.com` (or `http://localhost:8000` locally)

### Health Check

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Returns `{"message": "✅ Telecom Site Backend is running!"}` |

### Sites

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/sites` | List all sites. Query params: `include_archived` (bool), `sort_by` (`createdAt`, `updatedAt`, `name`, `siteType`, `region`), `sort_order` (`asc`/`desc`, default `desc`). |
| `GET` | `/sites/stats` | Site-wide stats: counts, completion %, expense breakdown. See below. |
| `GET` | `/sites/export` | Export all sites (with nested materials/activities/costs) + company settings as JSON. Auth required. |
| `POST` | `/sites/import` | Import sites from the same JSON shape as `/sites/export`. Skips duplicates. Auth required. |
| `POST` | `/sites/bulk-archive` | Archive multiple sites at once. Body: `["site_id_1", "site_id_2", ...]`. Auth required. |
| `POST` | `/sites/bulk-unarchive` | Unarchive multiple sites at once. Same body shape. Auth required. |
| `GET` | `/sites/{site_id}` | Get one site with all nested data. |
| `POST` | `/sites` | Create a site. |
| `PUT` | `/sites/{site_id}` | Update site fields. |
| `DELETE` | `/sites/{site_id}` | Delete a site (cascades to materials/activities/costs). |
| `POST` | `/sites/{site_id}/archive` | Archive a site. |
| `POST` | `/sites/{site_id}/unarchive` | Unarchive a site. |

**Sorting example:**

```bash
# Newest sites first (default sort_order)
GET /sites?sort_by=createdAt&sort_order=desc

# Oldest sites first — useful for a "founded" timeline view
GET /sites?sort_by=createdAt&sort_order=asc
```

**`POST /sites` request body:**

```json
{
  "name": "Kumasi Tower 3",                // required
  "laborCost": 5000.0,                     // optional, default 0
  "siteCode": "TEL-KMAS-AB12",             // optional, auto-generated if omitted
  "siteType": "4G",                        // optional — 4G, 5G, Fiber, etc.
  "region": "Ashanti",                     // optional — location/region
  "location": "Adum, Kumasi",              // optional — detailed location
  "latitude": 6.6851,                      // optional — GPS coordinates
  "longitude": -1.6218,                    // optional — GPS coordinates
  "googleMapsUrl": "https://maps.google.com/?q=6.6851,-1.6218",  // optional — Google Maps link
  "images": "[\"https://example.com/img1.jpg\",\"https://example.com/img2.jpg\"]",  // optional — JSON array of image URLs
  "notes": "Site has backup generator. Access via Adum main road.",  // optional — site notes
  "isArchived": false,                     // optional, default false
  "createdAt": "2025-06-15T09:30:00Z"      // optional, editable creation date (defaults to now)
}
```

**`PUT /sites/{site_id}`** accepts any subset of the same fields — including `createdAt` for backdating sites.

### Response Object — Site

A site response includes **everything nested**:

```json
{
  "id": "3f2c...",
  "name": "Kumasi Tower 3",
  "laborCost": 5000.0,
  "siteCode": "TEL-KMAS-AB12",
  "siteType": "4G",
  "region": "Ashanti",
  "location": "Adum, Kumasi",
  "latitude": 6.6851,
  "longitude": -1.6218,
  "googleMapsUrl": "https://maps.google.com/?q=6.6851,-1.6218",
  "images": "[\"https://example.com/img1.jpg\",\"https://example.com/img2.jpg\"]",
  "notes": "Site has backup generator. Access via Adum main road.",
  "isArchived": false,
  "createdAt": "2026-08-01T12:00:00+00:00",
  "updatedAt": "2026-08-01T12:00:00+00:00",
  "materials": [
    { "id": "m1", "name": "Cable", "quantity": 100.0, "unit": "m", "cost": 250.0 }
  ],
  "activities": [
    { "id": "a1", "name": "Install antenna", "completed": true, "isArchived": false, "activityDate": "2026-08-02T09:00:00+00:00", "startDatetime": "2026-08-02T09:00:00+00:00", "endDatetime": "2026-08-02T17:00:00+00:00" }
  ],
  "operationalCosts": [
    { "id": "oc1", "name": "Rent", "amount": 1200.0 }
  ]
}
```

### Site Stats — `GET /sites/stats`

Returns aggregate numbers for a dashboard: total sites, how many are "completed" (a site counts as completed once it has at least one non-archived activity and every non-archived activity on it is marked `completed`), and an expense breakdown (labor cost + materials cost + operational costs) grouped by the month/year the **site** was created. Add `?include_archived=true` to fold archived sites into the numbers.

```json
{
  "totalSites": 12,
  "archivedSites": 2,
  "completedSites": 5,
  "completedPercentage": 41.7,
  "expenses": {
    "totalLaborCost": 45000.0,
    "totalMaterialsCost": 12500.0,
    "totalOperationalCost": 3200.0,
    "totalExpenses": 60700.0,
    "monthly": [
      { "period": "2025-08", "laborCost": 5000.0, "materialsCost": 1200.0, "operationalCost": 0.0, "total": 6200.0 },
      { "period": "2026-02", "laborCost": 8000.0, "materialsCost": 3000.0, "operationalCost": 450.5, "total": 11450.5 }
    ],
    "yearly": [
      { "period": "2025", "laborCost": 5000.0, "materialsCost": 1200.0, "operationalCost": 0.0, "total": 6200.0 },
      { "period": "2026", "laborCost": 40000.0, "materialsCost": 11300.0, "operationalCost": 3200.0, "total": 54500.0 }
    ]
  }
}
```

### Import / Export — complete data transfer

`GET /sites/export` returns every site with all of its nested materials, activities, and operational costs, plus company settings — everything needed to fully reconstruct the data elsewhere. Feed that same JSON straight into `POST /sites/import` (on this instance or another) to bring the data back in.

**Duplicate detection on import:** a site is treated as a duplicate — and skipped, not overwritten — if either its `siteCode` matches an existing site's code, or its `name` + `location` pair matches an existing site (case-insensitive). Duplicates are also detected *within* the same import payload, so re-importing an export is always safe (idempotent) and importing a mixed batch only creates the genuinely new sites.

```bash
# Export everything (requires auth)
GET /sites/export
Authorization: Bearer <token>

# Import it back in (or into another instance) — matches are skipped automatically
POST /sites/import
Authorization: Bearer <token>
Content-Type: application/json

{ "sites": [ /* same shape as the "sites" array from /sites/export */ ] }
```

Response:

```json
{
  "message": "Imported 3 sites, skipped 1 duplicates",
  "importedCount": 3,
  "skippedCount": 1,
  "importedSiteIds": ["..."],
  "skipped": [
    { "name": "Kumasi Tower B", "siteCode": "TEL-KUMA-NIK3", "reason": "Duplicate of existing site 'Kumasi Tower B' (bc90fbb3-...)" }
  ]
}
```

### Bulk Archive Sites

Mirrors the activities bulk-archive pattern, for a "select multiple sites → archive" action on a sites list:

```bash
POST /sites/bulk-archive
Authorization: Bearer <token>
Content-Type: application/json

["site_id_1", "site_id_2"]
```

`POST /sites/bulk-unarchive` takes the same body shape and reverses it.

### Materials (nested under a site)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/sites/{site_id}/materials` | Add material. |
| `DELETE` | `/sites/{site_id}/materials/{material_id}` | Delete material. |

**`POST /sites/{site_id}/materials`:**

```json
{
  "name": "Fiber Optic Cable",
  "quantity": 500,
  "unit": "m",
  "cost": 750
}
```

### Activities (nested under a site)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/sites/{site_id}/activities` | List activities. Query params: `sort_by` (activityDate, startDatetime, endDatetime, createdAt, updatedAt, name), `sort_order` (asc/desc), `include_archived` (true/false). |
| `POST` | `/sites/{site_id}/activities` | Add activity. |
| `PATCH` | `/sites/{site_id}/activities/{activity_id}` | Update name / `completed` / `activityDate` / `startDatetime` / `endDatetime` / `isArchived`. |
| `DELETE` | `/sites/{site_id}/activities/{activity_id}` | Delete activity. |
| `POST` | `/sites/{site_id}/activities/bulk-archive` | Archive multiple activities at once (scrum-style). Body: `["activity_id_1", "activity_id_2", ...]` |
| `POST` | `/sites/{site_id}/activities/bulk-unarchive` | Unarchive multiple activities at once. Body: `["activity_id_1", "activity_id_2", ...]` |

**`POST /sites/{site_id}/activities`** (scrum-style sprint planning):

```json
{
  "name": "Tower erection",
  "completed": false,
  "activityDate": "2026-08-15T08:00:00Z",       // legacy single date
  "startDatetime": "2026-08-15T08:00:00Z",      // planned sprint start
  "endDatetime": "2026-08-15T17:00:00Z",        // planned sprint end
  "isArchived": false                            // archive completed sprints
}
```

**`PATCH /sites/{site_id}/activities/{activity_id}`** — partial update, e.g. toggle completion or archive:

```json
{ "completed": true, "isArchived": true }
```

**`GET /sites/{site_id}/activities`** — supports sorting & filtering:

```bash
# Sort by sprint start date (newest first), exclude archived (default)
GET /sites/{site_id}/activities?sort_by=startDatetime&sort_order=desc

# Include archived activities
GET /sites/{site_id}/activities?include_archived=true

# Sort by activity name (A-Z)
GET /sites/{site_id}/activities?sort_by=name&sort_order=asc
```

**Sortable fields:** `activityDate`, `startDatetime`, `endDatetime`, `createdAt`, `updatedAt`, `name`

---

### Activity Response Object

```json
{
  "id": "a1",
  "name": "Tower erection",
  "completed": true,
  "isArchived": false,
  "completedAt": "2026-08-15T16:00:00+00:00",
  "activityDate": "2026-08-15T08:00:00+00:00",
  "startDatetime": "2026-08-15T08:00:00+00:00",
  "endDatetime": "2026-08-15T17:00:00+00:00",
  "createdAt": "2026-08-01T12:00:00+00:00",
  "updatedAt": "2026-08-01T12:00:00+00:00"
}
```

### Operational Costs (nested under a site)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/sites/{site_id}/operational-costs` | Add operational cost. |
| `DELETE` | `/sites/{site_id}/operational-costs/{operational_cost_id}` | Delete operational cost. |

**`POST /sites/{site_id}/operational-costs`:**

```json
{
  "name": "Generator fuel",
  "amount": 450.50
}
```

### Company Settings

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/company-settings` | Get company name, logo, contact info. |
| `PUT` | `/company-settings` | Update any field. |

**`PUT /company-settings`:**

```json
{
  "name": "Nexus Telecom",
  "logoUrl": "https://example.com/logo.png",
  "email": "info@nexustelecom.com",
  "phone": "+233 55 123 4567",
  "address": "Accra, Ghana",
  "website": "https://nexustelecom.com"
}
```

---

## 🔧 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | ✅ Yes | PostgreSQL connection string (Neon is preconfigured in `.env`). Falls back to local SQLite (`telecom_sites.db`) if missing. |
| `PORT` | Optional | Injected by hosting platform. Defaults to `8000`. |
| `ENV` | Optional | Set to `development` for auto-reload. Any other value = production (no reload). |

---

## 🧪 Local Testing (optional)

```bash
pip install -r requirements.txt
python app.py
# → http://localhost:8000
```

Interactive API docs (Swagger UI) at **`http://localhost:8000/docs`** — great for testing endpoints from the browser.

---

## 🔐 Authentication

The API supports **two authentication methods**:

| Method | Use Case | Header Format |
|--------|----------|---------------|
| **JWT (username/password)** | Frontend login, user sessions | `Authorization: Bearer <jwt_token>` |
| **API Key** | Server-to-server, scripts, CI/CD | `Authorization: Bearer <tsk_...>` |

Both arrive via the same `Authorization: Bearer <token>` header — the backend detects which type by the token prefix.

### Default Seeded Users

On first startup (or when the `users` table is empty), the app automatically creates two users:

| Username | Password | Role | Capabilities |
|----------|----------|------|--------------|
| `admin` | `admin123` | `admin` | Full access — all endpoints + user management |
| `manager` | `manager123` | `manager` | Read/write sites, materials, activities, costs |

> ⚠️ **Change these passwords in production!** They're seeded for convenience only.

### Login (Get JWT Token)

```bash
POST /auth/login
Content-Type: application/json

{
  "username": "admin",
  "password": "admin123"
}
```

**Response (200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "username": "admin",
  "role": "admin"
}
```

**Errors:**
- `401 Invalid credentials` — wrong username/password

### Using the JWT Token

Include the token in subsequent requests:

```bash
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Token expiry:** 7 days (configurable via `ACCESS_TOKEN_EXPIRE_MINUTES` in `auth.py`).

### Role-Based Access

| Role | Can Access |
|------|------------|
| `admin` | All endpoints (future: user management, settings) |
| `manager` | All site/material/activity/cost CRUD, company settings |

Endpoints requiring auth use `Depends(get_current_active_user)` — returns `401` if missing/invalid, `403` if role insufficient.

### API Keys (Server-to-Server)

For automated access (CI/CD, scripts, external services), use the preconfigured API key:

```bash
Authorization: Bearer tsk_v7AcKSzC6Pe0caTyVuZk2FluUha_4CoBNDjRj1SHeZE
```

**Configure in `.env`:**
```env
VALID_API_KEYS=tsk_v7AcKSzC6Pe0caTyVuZk2FluUha_4CoBNDjRj1SHeZE
```
Comma-separate multiple keys. API keys have **admin-equivalent access**.

### Adding Custom Users (Manual)

Since there's no self-registration endpoint, **you control who gets access** by inserting directly into the database:

```python
# One-off script (run locally or in a shell)
from database import SessionLocal
from auth import create_user

db = SessionLocal()
create_user(db, "your_username", "you@example.com", "your_secure_password", "manager")
# role can be "admin" or "manager"
db.close()
```

Or via raw SQL (e.g., Neon dashboard, `psql`, DBeaver):

```sql
-- Password must be bcrypt-hashed. Generate hash first:
-- python -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('your_password'))"

INSERT INTO users (id, username, email, hashed_password, role, is_active, created_at, updated_at)
VALUES (
  gen_random_uuid(),
  'your_username',
  'you@example.com',
  '$2b$12$...hashed_password_here...',
  'manager',
  true,
  now(),
  now()
);
```

> ✅ **Only you can add users** — no public registration, no forgot-password flow. Full control.

### Frontend Login Page Example

```jsx
// React example
const login = async (username, password) => {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password })
  });
  
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Login failed');
  }
  
  const { access_token, username, role } = await res.json();
  
  // Store token (localStorage, httpOnly cookie, context, etc.)
  localStorage.setItem('auth_token', access_token);
  localStorage.setItem('user_role', role);
  localStorage.setItem('username', username);
  
  return { access_token, username, role };
};

// Authenticated fetch helper
const authFetch = (url, options = {}) => {
  const token = localStorage.getItem('auth_token');
  return fetch(url, {
    ...options,
    headers: {
      ...options.headers,
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    }
  });
};

// Usage
const sites = await authFetch(`${API_BASE}/sites`).then(r => r.json());
```

### Logout

Client-side only — delete the stored token:

```js
localStorage.removeItem('auth_token');
localStorage.removeItem('user_role');
localStorage.removeItem('username');
```

---

## 🗄️ Database

- **Cloud (production):** PostgreSQL via Neon — connection string in `.env`.
- **Local fallback:** SQLite at `telecom_sites.db` if `DATABASE_URL` is missing.
- **Migrations:** Tables are created automatically on startup (`Base.metadata.create_all`) and missing columns are added via `migrate_schema()` for PostgreSQL. No manual migration steps needed.

**Tables:** `sites`, `materials`, `activities`, `operational_costs`, `company_settings`, `users`

### Backdating existing data

`Site.createdAt` and `Activity` dates are editable, not just set-once-at-creation — `PUT /sites/{id}` and `PATCH /sites/{site_id}/activities/{id}` both accept `createdAt`/date fields at any time. To backfill realistic historical dates for seed/demo data (rather than everything showing "today"), see `update_dates.py` — a one-off script that sets specific sites/activities to hand-picked past dates by `siteCode`/activity name. Extend that script (or write a similar one-off) whenever a batch of existing records needs backdating; there's no need for a dedicated endpoint since the regular update endpoints already support it per-record.
