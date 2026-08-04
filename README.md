# Telecom Site Backend

FastAPI + PostgreSQL (Neon) REST API for managing telecom sites — materials, activities, operational costs, and company settings. Ready to deploy and connect straight to your frontend.

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
| `GET` | `/sites` | List all sites. Add `?include_archived=true` to include archived. |
| `GET` | `/sites/{site_id}` | Get one site with all nested data. |
| `POST` | `/sites` | Create a site. |
| `PUT` | `/sites/{site_id}` | Update site fields. |
| `DELETE` | `/sites/{site_id}` | Delete a site (cascades to materials/activities/costs). |
| `POST` | `/sites/{site_id}/archive` | Archive a site. |
| `POST` | `/sites/{site_id}/unarchive` | Unarchive a site. |

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
  "isArchived": false                      // optional, default false
}
```

**`PUT /sites/{site_id}`** accepts any subset of the same fields.

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
    { "id": "a1", "name": "Install antenna", "completed": true, "activityDate": "2026-08-02T09:00:00+00:00" }
  ],
  "operationalCosts": [
    { "id": "oc1", "name": "Rent", "amount": 1200.0 }
  ]
}
```

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
| `POST` | `/sites/{site_id}/activities` | Add activity. |
| `PATCH` | `/sites/{site_id}/activities/{activity_id}` | Update name / `completed` / `activityDate`. |
| `DELETE` | `/sites/{site_id}/activities/{activity_id}` | Delete activity. |

**`POST /sites/{site_id}/activities`:**

```json
{
  "name": "Tower erection",
  "completed": false,
  "activityDate": "2026-08-15T08:00:00Z"
}
```

**`PATCH /sites/{site_id}/activities/{activity_id}`** — partial update, e.g. toggle completion:

```json
{ "completed": true }
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

## 🗄️ Database

- **Cloud (production):** PostgreSQL via Neon — connection string in `.env`.
- **Local fallback:** SQLite at `telecom_sites.db` if `DATABASE_URL` is missing.
- **Migrations:** Tables are created automatically on startup (`Base.metadata.create_all`) and missing columns are added via `migrate_schema()` for PostgreSQL. No manual migration steps needed.

**Tables:** `sites`, `materials`, `activities`, `operational_costs`, `company_settings`