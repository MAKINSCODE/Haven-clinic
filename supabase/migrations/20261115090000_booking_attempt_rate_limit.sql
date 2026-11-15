CREATE TABLE public.booking_attempts (
    id VARCHAR NOT NULL PRIMARY KEY,
    email_hash VARCHAR NOT NULL,
    attempted_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX ix_booking_attempts_email_time
    ON public.booking_attempts (email_hash, attempted_at);

CREATE INDEX ix_booking_attempts_attempted_at
    ON public.booking_attempts (attempted_at);

ALTER TABLE public.booking_attempts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.booking_attempts FROM PUBLIC, anon, authenticated;
