import React, { useState } from "react";

import { makeIdempotencyKey, formatDateLong, formatTime } from "../format.js";

export default function BookingForm({
  slot,
  submitting,
  error,
  onBack,
  onConfirm,
}) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [attemptKey, setAttemptKey] = useState("");
  const [validationError, setValidationError] = useState("");

  function submit(event) {
    event.preventDefault();
    const patientName = name.trim();
    const patientEmail = email.trim().toLowerCase();
    if (!patientName || !patientEmail) {
      setValidationError("Enter your name and email address.");
      return;
    }

    setValidationError("");
    // Reuse this key when retrying unchanged form values after an uncertain response.
    const key = attemptKey || makeIdempotencyKey();
    setAttemptKey(key);
    onConfirm({ name: patientName, email: patientEmail, idempotencyKey: key });
  }

  return (
    <section className="stack" aria-labelledby="page-title">
      <div>
        <button className="text-button back-button" onClick={onBack} type="button">
          ← Back to appointments
        </button>
        <p className="eyebrow">YOUR DETAILS</p>
        <h1 id="page-title" className="title">Complete your booking.</h1>
      </div>

      <div className="booking-layout">
        <form className="form" onSubmit={submit} noValidate>
          <div className="field">
            <label htmlFor="patient-name">Full name</label>
            <input
              id="patient-name"
              name="name"
              autoComplete="name"
              required
              value={name}
              onChange={(event) => {
                setName(event.target.value);
                setAttemptKey("");
              }}
            />
          </div>
          <div className="field">
            <label htmlFor="patient-email">Email address</label>
            <input
              id="patient-email"
              name="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);
                setAttemptKey("");
              }}
            />
            <p className="hint">Use this email to find your booking later.</p>
          </div>
          {validationError || error ? (
            <p className="error-message" role="alert">{validationError || error}</p>
          ) : null}
          <button className="button button-primary" disabled={submitting} type="submit">
            {submitting ? "Confirming…" : "Confirm Booking"}
          </button>
        </form>

        <aside className="summary" aria-label="Selected appointment">
          <p className="eyebrow">YOUR APPOINTMENT</p>
          <p className="summary-time">{formatTime(slot.start)}</p>
          <hr />
          <p><strong>{slot.provider}</strong></p>
          <p>{formatDateLong(slot.start)}</p>
          <p className="muted">30 minutes</p>
        </aside>
      </div>
    </section>
  );
}