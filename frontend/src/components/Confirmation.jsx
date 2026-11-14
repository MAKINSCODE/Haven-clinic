import React from "react";

import { formatDateLong, formatTime } from "../format.js";

export default function Confirmation({ booking, slot, onViewBooking, onBookAnother }) {
  return (
    <section className="stack" aria-labelledby="page-title">
      <div>
        <p className="eyebrow">HAVEN CLINIC</p>
        <h1 id="page-title" className="title">Appointment confirmed.</h1>
        <p className="lead">
          Your appointment is booked. Keep this booking ID for your records.
        </p>
      </div>
      <dl className="confirmation-card">
        <div><dt>Booking ID</dt><dd className="booking-id">{booking.id}</dd></div>
        <div><dt>Patient</dt><dd>{booking.name}</dd></div>
        <div><dt>Email</dt><dd>{booking.email}</dd></div>
        <div><dt>Provider</dt><dd>{slot.provider}</dd></div>
        <div><dt>Date</dt><dd>{formatDateLong(slot.start)}</dd></div>
        <div><dt>Time</dt><dd>{formatTime(slot.start)}</dd></div>
        <div><dt>Status</dt><dd>{booking.status}</dd></div>
      </dl>
      <div className="action-row">
        <button className="button button-primary" onClick={onViewBooking} type="button">
          View Booking
        </button>
        <button className="button button-secondary" onClick={onBookAnother} type="button">
          Book another
        </button>
      </div>
    </section>
  );
}