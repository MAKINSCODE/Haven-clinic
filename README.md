# Clinic Appointment Booking System

## Level 5: booking API, idempotency, history, and rate limiting

The FastAPI backend uses SQLAlchemy and supports PostgreSQL. The `slots` and
`bookings` tables store appointment data; `booking_attempts` stores hashed-email
attempt timestamps for rate limiting.

### Setup

From the `backend` directory, create and activate a virtual environment and
install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Set `DATABASE_URL` to a Supabase PostgreSQL connection string for a development
or test project. If it is unset, the
backend uses a local SQLite database at `backend\clinic.db`.

Set `API_KEY` in the backend environment before starting the API. Every API
route requires this value in the `X-API-Key` request header. The React frontend
uses a server-side proxy to add this key; it is never included in browser code.

Run the seed script once to create the tables and insert fictional sample slots:

```powershell
python -m app.seed
```

The script adds its sample slot IDs only when they are not already present. It
does not run automatically when the API starts.

After deploying the latest code to an existing database, run this migration
once before serving booking requests. It adds the partial unique indexes and
nullable idempotency columns to `bookings`, and creates the `booking_attempts`
table and its indexes:

```powershell
python -m app.migrate
```

The migration stops with an explicit error if the database already contains
multiple confirmed bookings for a slot or duplicate non-null idempotency keys;
resolve those records before retrying.

Start the API from the `backend` directory:

```powershell
uvicorn app.main:app --reload
```

Available routes:

- `POST /reset`
- `GET /slots` with an optional exact-match `provider` query
- `POST /bookings`
- `GET /bookings/{id}`
- `DELETE /bookings/{id}` to cancel a booking
- `GET /bookings?email=...` with optional `limit` and `cursor`

Booking requests require a non-empty `slot_id`, `name`, and valid `email`.
Names and emails are trimmed, emails are stored lowercase, and bookings are
rejected if their slot does not exist, has already started, or has another
confirmed booking. Cancelling a booking makes its slot available again.

`POST /bookings` accepts an optional `Idempotency-Key` header. Reusing the key
with the same normalized request replays the original booking response; using
it with a different request returns `422`. Booking history is filtered by
email, ordered oldest first, and uses an opaque cursor based on creation time
and booking ID. The `limit` is between 1 and 50 and defaults to 10.

`GET /slots` returns `{"slots": [...]}`. `POST /bookings` limits each email to
five attempts in a rolling minute, including requests that later fail booking
validation or rules. The sixth attempt returns `429` and a `Retry-After`
header. Attempt records contain an HMAC of the normalized email, not the email
itself, and expired records are removed as new attempts arrive.

## Supabase CLI and PostgreSQL

The Supabase CLI project config is in `supabase\`. Run the pinned CLI version
through `npx` (Node.js 20 or later) without installing a global executable:

```powershell
npx --yes supabase@3.1.0 --version
```

Create a new development/test project in the Supabase Dashboard and save its
database password securely. From the repository root, authenticate and link
the CLI. `login` prompts for a Supabase personal access token; `link` prompts
for the database password. Do not put either secret in Git or in browser code.

```powershell
npx --yes supabase@3.1.0 login
npx --yes supabase@3.1.0 link --project-ref "your-project-ref"
```

The initial migration creates the `slots` and `bookings` tables, booking
uniqueness indexes, and row-level security. The later rate-limiting migration
creates `booking_attempts` and its indexes, also with row-level security and
revoked direct table access. The FastAPI backend connects with server-side
PostgreSQL credentials. Review the migrations, then apply them to the linked
hosted project with
`--remote`. Without that flag, the CLI targets the local Supabase stack and
requires Docker. Apply the baseline migration only to a new, empty project.
On an existing project with the initial migration recorded, this applies only
new migrations:

```powershell
npx --yes supabase@3.1.0 db push --remote
```

Set `DATABASE_URL` in the backend terminal to the connection string from the
Supabase Dashboard's **Connect** dialog. If a direct connection is unavailable
on your network, use the Supabase session pooler connection string. Then run
the existing idempotent seed script once to add the current sample slots:

```powershell
Set-Location backend
$env:DATABASE_URL = "paste-your-development-project-connection-string-here"
python -m app.seed
```

The CLI's `supabase\seed.sql` mirrors `backend\app\seed.py` for local Supabase
resets. Remote database initialization uses the Python seed command above.
Do not run the baseline migration against a project that already has these
tables; inspect and pull an existing schema first.

### Tests

Run from the `backend` directory:

```powershell
pytest
```

## React frontend

Start the backend from the `backend` directory as described above. Then, in a
second terminal, configure and start the frontend:

```powershell
cd ..\frontend
Copy-Item .env.example .env.local
npm install
npm run dev
```

Set `API_KEY` in `frontend\.env.local` to the same value configured for the
backend. `BACKEND_API_URL` defaults to `http://127.0.0.1:8000`; change it if
the API is running elsewhere. The Vite development proxy reads these values
server-side. For a Vercel deployment, configure `BACKEND_API_URL` and `API_KEY`
as server environment variables for the frontend project.

The UI loads available providers and appointment times from `GET /slots`,
creates bookings with `POST /bookings`, and uses the existing booking lookup,
history, and cancellation endpoints. No mock slot or booking data is duplicated
in the frontend.