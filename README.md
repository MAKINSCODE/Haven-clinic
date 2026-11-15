# Haven Clinic Appointment Booking

Haven Clinic helps patients find, book, and manage appointments.

## The problem

Patients need a simple way to book appointments, while the clinic needs reliable
availability, safe handling of retries and concurrent requests, and searchable
booking records.

## The solution

A React frontend and FastAPI backend use one persistent Supabase PostgreSQL
database. The API enforces booking rules. A server-side proxy keeps the API key
out of browser code. The backend requires PostgreSQL and loads `DATABASE_URL`
from `backend\.env` locally.

## Development levels

1. **Basic API:** Store slots and bookings; list availability and create bookings.
2. **Authentication and validation:** Require an API key; validate and normalize
   booking details.
3. **Booking protection:** Prevent double bookings, handle concurrent requests,
   and allow cancellations to free slots.
4. **Idempotency and history:** Safely replay retries, find bookings by ID, and
   page through email-filtered history.
5. **Rate limiting and patient flows:** Limit attempts per email and complete
   frontend booking, lookup, history, and cancellation flows.

## Challenges and engineering decisions

- PostgreSQL row locks and partial unique indexes protect slot availability.
- Idempotency keys and normalized request fingerprints make retries safe.
- Email normalization and stable cursor ordering make history predictable.
- The API key stays server-side; rate-limit records store an HMAC of email.
- Tests use temporary PostgreSQL schemas, keeping the project on one database
  engine.

## Result

Patients can view provider-filtered availability, book an appointment, find it
by ID or email, review paginated history, and cancel a confirmed booking.
Invalid or unavailable slots are rejected; the sixth booking attempt for an
email within one minute receives HTTP `429`. Fictional sample slots are
available for development.

**Stack:** React, Vite, Python 3.12, FastAPI, SQLAlchemy, Psycopg,
Supabase PostgreSQL, and Vercel.

## Run locally

Use Python 3.12, Node.js, npm, and a Supabase PostgreSQL project reserved for
development/testing. Never run local tests against production.

### Configure PostgreSQL

From `backend`, create `.env` from the root example:

```powershell
Copy-Item ..\.env.example .env
```

Set `DATABASE_URL` to the Supabase Dashboard connection string and `API_KEY`
to a long random secret. Use a pooler URL if a direct connection is unavailable.
Keep `.env` private.

Apply migrations only after reviewing the target project and migration history:

```powershell
npx --yes supabase@3.1.0 login
npx --yes supabase@3.1.0 link --project-ref "your-project-ref"
npx --yes supabase@3.1.0 db push --remote
```

`--remote` targets the linked hosted project. Apply the baseline migration only
to a new, empty database. Reconcile existing tables without migration history
before pushing. For an existing database with the original `slots` and
`bookings` tables, run `python -m app.migrate` from `backend` to add the newer
booking and rate-limit storage.

### Start the backend

From `backend`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.seed
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The seed command adds missing fictional slots; it does not clear bookings or
replace existing slots.

### Start the frontend

In another terminal:

```powershell
cd frontend
Copy-Item .env.example .env.local
npm ci
npm run dev -- --host 127.0.0.1
```

Set `API_KEY` in `frontend\.env.local` to match `backend\.env`.
`BACKEND_API_URL` defaults to `http://127.0.0.1:8000`.

- App: <http://127.0.0.1:5173>
- API docs: <http://127.0.0.1:8000/docs>

The frontend proxy adds the required `X-API-Key` header server-side.

> **Warning:** `POST /reset` deletes all bookings and slots, then replaces
> slots from its request. Use only with a development/test database. The
> deployed frontend proxy does not expose this route.

## API

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/slots` | List slots; optionally filter by provider |
| `POST` | `/bookings` | Create booking; optional `Idempotency-Key` |
| `GET` | `/bookings/{id}` | Find a booking |
| `GET` | `/bookings?email=...` | Email history; optional `limit` and `cursor` |
| `DELETE` | `/bookings/{id}` | Cancel a booking |
| `POST` | `/reset` | Replace slots and delete bookings (development only) |

History defaults to 10 results per page; `limit` can be 1–50.

## Tests

From `backend`, run `pytest`. Tests create and drop isolated schemas in the
configured database: use a development/test project, never production.

From `frontend`, run:

```powershell
npm test
npm run build
```

## Deploy to Vercel

Create separate backend and frontend projects from this repository:

1. **Backend:** Root Directory `backend`; configure server-side `DATABASE_URL`
   and `API_KEY`. Use persistent Supabase PostgreSQL and enable Vercel System
   Environment Variables.
2. **Frontend:** Root Directory `frontend`; build with `npm run build`, output
   `dist`; set `BACKEND_API_URL` to the backend HTTPS origin and `API_KEY` to
   the same secret.

Apply reviewed migrations before deploying the backend. Deploy it first, then
configure its URL and deploy the frontend. Its `/api` proxy forwards supported
routes and adds the key server-side.
