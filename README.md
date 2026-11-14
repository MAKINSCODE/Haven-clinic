# Clinic Appointment Booking System

## Level 3: protected booking and cancellation API

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
route requires this value in the `X-API-Key` request header. Do not put this
secret in React/browser code; when the patient UI is implemented, its requests
must pass through a server-side function configured with the same environment
variable. The current frontend files are placeholders and do not contain a
booking flow.

Run the seed script once to create the tables and insert fictional sample slots:

```powershell
python -m app.seed
```

The script adds its sample slot IDs only when they are not already present. It
does not run automatically when the API starts.

After deploying the Level 3 code to an existing database, run this migration
once before serving booking requests. It adds a partial unique index so the
database itself permits at most one confirmed booking per slot while allowing
cancelled bookings to remain:

```powershell
python -m app.migrate
```

The migration stops with an explicit error if the database already contains
multiple confirmed bookings for a slot; resolve those records before retrying.

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

Booking requests require a non-empty `slot_id`, `name`, and valid `email`.
Names and emails are trimmed, emails are stored lowercase, and bookings are
rejected if their slot does not exist, has already started, or has another
confirmed booking. Cancelling a booking makes its slot available again.

### Tests

Run from the `backend` directory:

```powershell
pytest
```