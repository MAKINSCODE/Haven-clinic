# Clinic Appointment Booking System

## Level 4: idempotency and booking history API

This level implements the basic REST API with a FastAPI backend, SQLAlchemy
models, and PostgreSQL support. Exactly two tables are used: `slots` and
`bookings`.

### Setup

From the `backend` directory, create and activate a virtual environment and
install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Set `DATABASE_URL` to a Neon PostgreSQL connection string. If it is unset, the
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
nullable idempotency columns to the existing `bookings` table:

```powershell
python -m app.migrate
```

The migration stops with an explicit error if the database already contains
multiple confirmed bookings for a slot or duplicate non-null idempotency keys;
resolve those records before retrying. It does not create another table.

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