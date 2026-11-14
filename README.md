# Clinic Appointment Booking System

## Level 1: basic booking API

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

Run the seed script once to create the tables and insert fictional sample slots:

```powershell
python -m app.seed
```

The script adds its sample slot IDs only when they are not already present. It
does not run automatically when the API starts.

Start the API from the `backend` directory:

```powershell
uvicorn app.main:app --reload
```

Available routes:

- `POST /reset`
- `GET /slots` with an optional exact-match `provider` query
- `POST /bookings`
- `GET /bookings/{id}`

### Tests

Run from the `backend` directory:

```powershell
pytest
```