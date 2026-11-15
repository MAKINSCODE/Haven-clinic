import React, { useCallback, useEffect, useState } from "react";

import { getBooking, getSlots } from "../api.js";
import { formatDateLong, formatTime } from "../format.js";

export default function FindBooking({ initialBookingId = "" }) {
  const [bookingId, setBookingId] = useState(initialBookingId);
  const [booking, setBooking] = useState(null);
  const [slot, setSlot] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [slotWarning, setSlotWarning] = useState("");

  const findBooking = useCallback(async (value) => {
    const id = value.trim();
    if (!id) {
      setError("Enter your booking ID.");
      return;
    }

    setLoading(true);
    setError("");
    setSlotWarning("");
    setBooking(null);
    setSlot(null);
    try {
      const [bookingResult, slotsResult] = await Promise.allSettled([
        getBooking(id),
        getSlots(),
      ]);
      if (bookingResult.status === "rejected") {
        setError(
          bookingResult.reason instanceof Error
            ? bookingResult.reason.message
            : "Could not load this booking.",
        );
        return;
      }

      const foundBooking = bookingResult.value;
      setBooking(foundBooking);
      if (slotsResult.status === "rejected") {
        setSlotWarning(
          "Appointment details could not be loaded. Booking details are still shown.",
        );
      } else {
        const matchingSlot = slotsResult.value.find(
          (item) => item.id === foundBooking.slot_id,
        );
        if (matchingSlot) {
          setSlot(matchingSlot);
        } else {
          setSlotWarning("Appointment slot details are no longer available.");
        }
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setBookingId(initialBookingId);
    setBooking(null);
    setError("");
    if (initialBookingId) {
      findBooking(initialBookingId);
    }
  }, [findBooking, initialBookingId]);

  return (
    <section className="stack" aria-labelledby="page-title">
      <div>
        <p className="eyebrow">FIND A BOOKING</p>
        <h1 id="page-title" className="title">Find booking</h1>
        <p className="lead">Enter your booking ID to view its details.</p>
      </div>

      <form
        className="history-search"
        onSubmit={(event) => {
          event.preventDefault();
          findBooking(bookingId);
        }}
      >
        <div className="field">
          <label htmlFor="booking-id">Booking ID</label>
          <input
            id="booking-id"
            type="text"
            autoComplete="off"
            required
            value={bookingId}
            onChange={(event) => setBookingId(event.target.value)}
            placeholder="Enter your booking ID"
          />
        </div>
        <button className="button button-primary" type="submit" disabled={loading}>
          {loading ? "Searching…" : "Find booking"}
        </button>
      </form>

      {error ? <p className="error-message" role="alert">{error}</p> : null}
      {slotWarning ? <p className="muted" role="status">{slotWarning}</p> : null}
      {booking ? (
        <article className="booking-card">
          <div className="booking-card-top">
            <div>
              <p className="eyebrow">BOOKING</p>
              <p className="booking-id">{booking.id}</p>
            </div>
            <span className={`status status-${booking.status}`}>{booking.status}</span>
          </div>
          <dl className="confirmation-card">
            <div><dt>Patient</dt><dd>{booking.name}</dd></div>
            <div><dt>Email</dt><dd>{booking.email}</dd></div>
            {slot ? (
              <>
                <div><dt>Provider</dt><dd>{slot.provider}</dd></div>
                <div><dt>Appointment date</dt><dd>{formatDateLong(slot.start)}</dd></div>
                <div><dt>Appointment time</dt><dd>{formatTime(slot.start)}</dd></div>
              </>
            ) : null}
            <div>
              <dt>Date</dt>
              <dd>{new Date(booking.created_at).toLocaleString()}</dd>
            </div>
          </dl>
        </article>
      ) : null}
    </section>
  );
}
