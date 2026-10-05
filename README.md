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
   | **Start Command** | `gunicorn app:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT --timeout 120` |
   | **Environment** | Add `DATABASE_URL` (already in your `.env`) and `GEMINI_API_KEY` (for the AI assistant) |

   ⚠️ **`--timeout 120` matters.** Gunicorn defaults to 30s, which is shorter than a multi-step AI answer — the worker gets killed and the caller sees a 502. Also note that a Start Command set in the Render dashboard **overrides the `Procfile`**, so the flag has to be in whichever one your service actually uses. If you'd rather the `Procfile` be the single source of truth, clear the Start Command field in the dashboard.
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

## 🤖 AI Assistant

A chat assistant that answers questions about the live data, draws charts, and builds slide decks. It runs on a **free** model — Google's Gemini free tier by default.

### Setup (2 minutes)

1. Get a free API key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey) — no credit card needed.
2. Set `GEMINI_API_KEY` in your `.env` locally, and as an environment variable on Render.
3. Restart. `GET /ai/status` should report `{"enabled": true}`.

### Rate limits, and why you probably won't notice them

Gemini's free tier is **metered per model** and the newer models are stingy — `gemini-3.6-flash` allows on the order of 20 requests before it starts refusing, and one question costs 2–6 requests. On its own that means a handful of questions before you hit a wall.

So the assistant doesn't rely on one model. `get_provider()` builds a **failover chain**, and a quota refusal moves quietly to the next entry:

```
gemini-3.6-flash  ->  gemini-3.5-flash  ->  gemini-3.1-flash-lite
```

Measured: six questions fired back to back with no pauses, all six answered, riding down the chain as each bucket emptied. Only quota refusals and provider outages advance the chain — a genuine error surfaces immediately rather than being retried three times.

Two details worth knowing if you change this:

- Once a model answers, the conversation **stays** with it. Gemini 3.x tool calls carry a thought signature that only their author can replay, so drifting back to the primary mid-conversation breaks it.
- A tool call inherited from a different model is flattened to plain text rather than replayed as a function call, for the same reason.

Configure with `AI_MODEL_FALLBACKS` (comma-separated), or set `AI_DISABLE_PROVIDER_FAILOVER=1` to keep it on one provider.

**Adding a Groq key is the single biggest improvement.** Set `GROQ_API_KEY` and it joins the chain automatically; set `AI_PROVIDER=groq` to lead with it. Measured against Gemini on the same questions, Groq answered in **2–5s versus 8–16s**.

With `AI_PROVIDER=groq` and both keys set, the chain is six models across two providers:

```
openai/gpt-oss-120b -> openai/gpt-oss-20b -> qwen/qwen3.8-27b
  -> qwen/qwen3.6-27b -> openai/gpt-oss-safeguard-20b -> gemini-3.6-flash
```

Six back-to-back questions, no pauses: 6/6 answered.

> ⚠️ **Both providers retire models without warning.** `gemini-2.5-flash` and `llama-3.3-70b-versatile` were both defaults here and both now 404. If the assistant starts failing with "model does not exist", list what your key can actually reach — `GET https://api.groq.com/openai/v1/models` or `GET https://generativelanguage.googleapis.com/v1beta/models` — and update `AI_MODEL` / `AI_MODEL_FALLBACKS`. No code change needed.

### Why the chain needs several models

One round trip carries about **2,000 tokens of fixed overhead** — roughly 450 for the system prompt and 1,600 for the ten tool schemas — before any conversation content. Groq's free tier meters 8,000 tokens per minute *per model*, so a single model sustains only ~3 requests/minute, and one question costs 2–6 requests. Listing several models multiplies that budget, which is why the fallback list is long rather than a token nicety.

### Deploying it (Render)

1. Push. Render rebuilds and installs `httpx` + `python-pptx` from `requirements.txt`.
2. In the Render dashboard → **Environment**, add `GEMINI_API_KEY`. This is the only manual step; without it every other endpoint still works and `/ai/status` returns `{"enabled": false}`.
3. Hit `GET /ai/status` with a Bearer token to confirm.

Two things about the deployment that the assistant depends on:

- **The `Procfile` sets `--timeout 120`.** Gunicorn's default is 30s, which is shorter than a multi-step AI answer on a free-tier model — the worker gets killed mid-request and the caller sees a 502. Don't remove it.
- **`AI_TOTAL_BUDGET` (default 90s) is the wall-clock budget for one question.** When it runs out the model is told to answer from what it already has instead of calling more tools. Keep it comfortably below the gunicorn timeout.

On Render's free tier the service also sleeps after 15 minutes idle, so the first request after a quiet spell pays a ~50s cold start before the model is even reached. The web UI waits up to 150s and then suggests trying again.

### How it answers (and why the numbers are right)

The model **never sees the database and never writes SQL**. It is given a fixed set of read-only tools — `list_sites`, `aggregate_costs`, `list_activities`, `get_site_details`, and so on — and can only pick a tool and fill in its typed arguments. The server runs the query, returns JSON, and the model answers from that. Consequences worth knowing:

- Figures come from real queries, so it cannot invent a total.
- A question it has no tool for gets "I can't answer that from this data" rather than a guess.
- It is strictly read-only. It cannot create, edit, archive or delete anything.
- Archived records are excluded unless the question asks for them.

Charts and decks are produced through the same mechanism: `create_chart` and `create_presentation` are tools, so the structured output is validated server-side before it reaches the browser.

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/ai/status` | Whether the assistant is configured, and which model is in use. |
| `POST` | `/ai/chat` | Ask a question. Returns the answer plus any charts/deck. |
| `POST` | `/ai/presentation.pptx` | Render a returned deck as a downloadable PowerPoint file. |

All three require a Bearer token, like the rest of the API.

```bash
curl -X POST https://your-api/ai/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "Which region has the highest material costs?"}'
```

**Response shape:**

```json
{
  "answer": "Eastern is the most expensive region at GHS 149,830.00 ...",
  "charts": [
    {
      "title": "Total cost by region",
      "type": "bar",
      "categories": ["Eastern", "Ashanti"],
      "series": [{ "name": "Materials", "values": [137380.0, 111535.0] }],
      "xLabel": "",
      "yLabel": "Cost (GHS)"
    }
  ],
  "presentation": {
    "title": "Regional Cost Review",
    "subtitle": "Generated from live site data",
    "slides": [
      { "title": "Where the money goes", "bullets": ["..."], "chartIndex": 0, "notes": "" }
    ]
  },
  "toolsUsed": ["aggregate_costs", "create_chart"],
  "provider": "gemini",
  "model": "gemini-3.6-flash"
}
```

`charts` is `[]` and `presentation` is `null` when the question didn't call for them. Pass previous turns back as `history` (`[{role, content}]`) for follow-up questions.

To download a deck, POST the `presentation` and `charts` objects straight back to `/ai/presentation.pptx`; it streams a `.pptx` with native, editable PowerPoint charts.

### Code layout

| File | Purpose |
|------|---------|
| `ai/provider.py` | Provider adapters (Gemini + any OpenAI-compatible endpoint) behind one interface. |
| `ai/tools.py` | The read-only data tools and their JSON Schemas. Add a tool here to widen what the assistant can answer. |
| `ai/agent.py` | The tool-calling loop, system prompt, and chart/deck validation. |
| `ai/slides.py` | PowerPoint generation via `python-pptx`. |
| `ai/routes.py` | The three endpoints above. |

The router is mounted defensively in `app.py` — if the AI dependencies are missing, the rest of the API still boots and `/ai/status` explains why the assistant is off.

---

## 🔧 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | ✅ Yes | PostgreSQL connection string (Neon is preconfigured in `.env`). Falls back to local SQLite (`telecom_sites.db`) if missing. |
| `PORT` | Optional | Injected by hosting platform. Defaults to `8000`. |
| `ENV` | Optional | Set to `development` for auto-reload. Any other value = production (no reload). |
| `SECRET_KEY` | Recommended | Signs session tokens. Long random string. Generated and stored in the DB if unset. |
| `SIGNUP_ACCESS_CODE` | Optional | Access phrase for manager sign-ups. Unset (with the admin one) = sign-up off. |
| `ADMIN_SIGNUP_ACCESS_CODE` | Optional | Access phrase for admin sign-ups. |
| `RESEND_API_KEY` | For resets | Resend API key used to email password-reset links. |
| `RESEND_FROM_EMAIL` | For resets | Sender, on a domain verified in Resend. |
| `FRONTEND_URL` | For resets | Base URL of the web app, used in reset links. |
| `VALID_API_KEYS` | Optional | Comma-separated `tsk_...` keys for machine access (admin rights). |
| `WEB_CONCURRENCY` | Optional | Gunicorn workers (default 2 — right for Render's 512 MB free instance). |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | Optional | Postgres connection pool per worker (defaults 5 / 10). |
| `GEMINI_API_KEY` | For AI | Free key from [Google AI Studio](https://aistudio.google.com/apikey). Without it the AI assistant reports itself unavailable; the rest of the API is unaffected. |
| `AI_PROVIDER` | Optional | `gemini` (default), `groq`, `openrouter`, or `ollama`. |
| `AI_MODEL` | Optional | Override the primary model. Defaults: `gemini-3.6-flash`, `openai/gpt-oss-120b` (groq), `meta-llama/llama-3.3-70b-instruct:free` (openrouter), `llama3.1` (ollama). |
| `AI_MODEL_FALLBACKS` | Optional | Comma-separated models to try when the primary is rate limited. Defaults to `gemini-3.5-flash,gemini-3.1-flash-lite` for Gemini. |
| `GROQ_API_KEY` | Optional | Free key from [console.groq.com](https://console.groq.com). Far more generous than Gemini; auto-appended to the failover chain when set. |
| `AI_DISABLE_PROVIDER_FAILOVER` | Optional | Set to `1` to keep the chain within one provider. |
| `AI_REQUEST_TIMEOUT` | Optional | Seconds to wait on a single model call. Defaults to `60`. |
| `AI_TOTAL_BUDGET` | Optional | Wall-clock seconds for one whole question, across all tool round-trips. Defaults to `90`. Must stay below the gunicorn `--timeout` in the `Procfile`. |

See `.env.example` for a copy-paste starting point.

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

People sign in with **email and password**. There are no built-in default accounts.

| Method | Use case | Header |
|--------|----------|--------|
| **Session token (JWT)** | The web app | `Authorization: Bearer <jwt>` |
| **API key** | Scripts, CI, server-to-server | `Authorization: Bearer tsk_...` |

Every data endpoint (sites, stats, export, company settings, AI) needs one of these. Only `/`, `/healthz` and the `/auth/*` routes below are public.

### Who can create an account

Sign-up needs an **access phrase** you hand out, so random visitors can't register:

| Variable | Effect |
|----------|--------|
| `SIGNUP_ACCESS_CODE` | Anyone who signs up with this phrase becomes a **manager**. |
| `ADMIN_SIGNUP_ACCESS_CODE` | Anyone who signs up with this phrase becomes an **admin**. |

Leave both unset to switch sign-up off completely (the sign-in screen then says "Ask your administrator"). Change a phrase at any time; existing accounts are unaffected.

> **First admin:** set `ADMIN_SIGNUP_ACCESS_CODE`, sign up once with it, then unset it (or change it) so nobody else can become an admin.

### Password resets (Resend)

"Forgot password?" emails a single-use link that expires after 30 minutes. Only a SHA-256 hash of the link's token is stored. Asking for a reset always returns the same message, so the endpoint can't be used to discover which emails have accounts. Resetting the password signs the person out everywhere else.

1. Create a free account at [resend.com](https://resend.com) and an API key.
2. Verify your sending domain in Resend (or use `onboarding@resend.dev` for testing, which only delivers to your own Resend login email).
3. Set `RESEND_API_KEY`, `RESEND_FROM_EMAIL` (e.g. `Telecom Site Manager <no-reply@yourdomain.com>`) and `FRONTEND_URL` (your deployed web app, used to build the link).

Without `RESEND_API_KEY` the email is printed to the server log instead, which is handy locally.

### Endpoints

| Method | Path | Body | Notes |
|--------|------|------|-------|
| `GET` | `/auth/config` | – | `{ "signupEnabled": true }` |
| `POST` | `/auth/login` | `{ "email", "password" }` | Returns a token. Email is case-insensitive. |
| `POST` | `/auth/signup` | `{ "email", "username", "password", "accessCode" }` | Password ≥ 8 chars, username 3–32 of `A-Z a-z 0-9 . _ -`. Returns a token. |
| `POST` | `/auth/forgot-password` | `{ "email" }` | Always `200` with the same message. |
| `POST` | `/auth/reset-password` | `{ "token", "password" }` | Returns a token (signs the person in). |
| `GET` | `/auth/me` | – | Current user's `username`, `email`, `role`. |

Token response:

```json
{
  "access_token": "eyJhbGciOi...",
  "token_type": "bearer",
  "username": "ama.k",
  "email": "ama@company.com",
  "role": "manager"
}
```

Login, sign-up and reset requests are rate limited per IP (HTTP `429` with a readable message).

### Sessions

- Tokens last 7 days (`ACCESS_TOKEN_EXPIRE_MINUTES` to change).
- Set `SECRET_KEY` to a long random string in production. If it's unset, one is generated on first boot and stored in the `app_config` table so every worker shares it.
- Changing a password invalidates all of that person's existing tokens.

### Old default accounts

Earlier versions created `admin / admin123` and `manager / manager123` and reset those passwords on every boot. Those two accounts are now **switched off automatically** at startup. Create real accounts with the sign-up flow above.

### API keys

Set `VALID_API_KEYS` (comma-separated, each starting with `tsk_`) for scripts and integrations. API keys have admin access, so keep them out of the repository. Generate one with:

```bash
python -c "import secrets; print('tsk_' + secrets.token_urlsafe(32))"
```

### Adding a user by hand

```python
from database import SessionLocal
from auth import create_user

db = SessionLocal()
create_user(db, "ama.k", "ama@company.com", "a-long-password", "manager")  # or "admin"
db.close()
```

### Tests

```bash
pip install pytest
pytest test_auth.py -q
```

---

## ⚡ Performance notes

- **Sites load in 4 queries, whatever the count.** Materials, activities and costs are batch-loaded (`selectinload`) instead of one query per site per relation, which was the main cause of slow loads against a remote Neon database.
- **Stats are computed by the database** with `SUM`/`COUNT ... GROUP BY` rather than loading every row.
- **Indexes** on every `site_id` foreign key, `sites.is_archived` and `lower(users.email)` are created automatically at startup.
- **Connection pooling** keeps warm TLS connections to Postgres (`pool_pre_ping` + `pool_recycle` handle Neon's idle shutdowns).
- **Gzip** compresses JSON responses over 1 KB.
- **Cold starts:** Render's free tier sleeps after 15 idle minutes and the next request waits ~50 s. `.github/workflows/keep-warm.yml` pings `/healthz` every 10 minutes to prevent that (set the `BACKEND_URL` repository variable if your URL differs). One always-on service fits in Render's 750 free hours a month.

---

## 🗄️ Database

- **Cloud (production):** PostgreSQL via Neon — connection string in `.env`.
- **Local fallback:** SQLite at `telecom_sites.db` if `DATABASE_URL` is missing.
- **Migrations:** Tables are created automatically on startup (`Base.metadata.create_all`) and missing columns are added via `migrate_schema()` for PostgreSQL. No manual migration steps needed.

**Tables:** `sites`, `materials`, `activities`, `operational_costs`, `company_settings`, `users`

### Backdating existing data

`Site.createdAt` and `Activity` dates are editable, not just set-once-at-creation — `PUT /sites/{id}` and `PATCH /sites/{site_id}/activities/{id}` both accept `createdAt`/date fields at any time. To backfill realistic historical dates for seed/demo data (rather than everything showing "today"), see `update_dates.py` — a one-off script that sets specific sites/activities to hand-picked past dates by `siteCode`/activity name. Extend that script (or write a similar one-off) whenever a batch of existing records needs backdating; there's no need for a dedicated endpoint since the regular update endpoints already support it per-record.
