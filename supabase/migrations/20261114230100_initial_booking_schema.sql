CREATE TABLE public.slots (
    id VARCHAR NOT NULL PRIMARY KEY,
    provider VARCHAR NOT NULL,
    start TIMESTAMP WITH TIME ZONE NOT NULL,
    "end" TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE public.bookings (
    id VARCHAR NOT NULL PRIMARY KEY,
    slot_id VARCHAR NOT NULL REFERENCES public.slots (id),
    name VARCHAR NOT NULL,
    email VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    idempotency_key VARCHAR,
    request_fingerprint VARCHAR,
    idempotency_response JSON,
    idempotency_status_code INTEGER
);

CREATE UNIQUE INDEX uq_bookings_one_confirmed_per_slot
    ON public.bookings (slot_id)
    WHERE status = 'confirmed';

CREATE UNIQUE INDEX uq_bookings_idempotency_key
    ON public.bookings (idempotency_key)
    WHERE idempotency_key IS NOT NULL;

ALTER TABLE public.slots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.bookings ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.slots, public.bookings FROM PUBLIC, anon, authenticated;
