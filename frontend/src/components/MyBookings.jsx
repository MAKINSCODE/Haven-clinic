import React, { useEffect, useState } from "react";

import { cancelBooking, getBookingHistory, getSlots } from "../api.js";
import { formatDateLong, formatTime } from "../format.js";

function AppointmentDetails({ slot }) {
  return (
    <div className="booking-details">
      <p><strong>{slot ? formatDateLong(slot.start) : "Appointment details"}</strong></p>
      <p>
        {slot
          ? `${formatTime(slot.start)} · ${slot.provider}`
          : "Provider and time are unavailable."}
      </p>
    </div>
  );
}

function BookingCard({
  booking,
  slot,
  highlighted,
  cancelling,
  pendingCancel,
  onRequestCancel,
  onKeep,
  onConfirmCancel,
}) {
  return (
    <article className={`booking-card${highlighted ? " booking-card-highlight" : ""}`}>
      <div className="booking-card-top">
        <div>
          <p className="eyebrow">BOOKING</p>
          <p className="booking-id">{booking.id}</p>
        </div>
        <span className={`status status-${booking.status}`}>{booking.status}</span>
      </div>
      <AppointmentDetails slot={slot} />
      <p className="booking-patient">{booking.name} <span>·</span> {booking.email}</p>
      {booking.status === "confirmed" ? (
        pendingCancel ? (
          <div className="cancel-confirm">
            <p>Cancel this appointment?</p>
            <button className="text-button" type="button" onClick={onKeep} disabled={cancelling}>
              Keep booking
            </button>
            <button
              className="text-button danger-text"
              type="button"
              onClick={onConfirmCancel}
              disabled={cancelling}
            >
              {cancelling ? "Cancelling…" : "Confirm cancellation"}
            </button>
          </div>
        ) : (
          <button className="text-button danger-text" type="button" onClick={onRequestCancel}>
            Cancel booking
          </button>
        )
      ) : null}
    </article>
  );
}

export default function MyBookings({ initialBooking = null }) {
  const [email, setEmail] = useState(initialBooking?.email || "");
  const [searchedEmail, setSearchedEmail] = useState("");
  const [pages, setPages] = useState([]);
  const [pageIndex, setPageIndex] = useState(0);
  const [selectedBooking, setSelectedBooking] = useState(initialBooking);
  const [slotsById, setSlotsById] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [slotWarning, setSlotWarning] = useState("");
  const [notice, setNotice] = useState("");
  const [pendingCancel, setPendingCancel] = useState("");
  const [cancellingId, setCancellingId] = useState("");

  useEffect(() => {
    let active = true;
    getSlots()
      .then((slots) => {
        if (active) {
          setSlotsById(Object.fromEntries(slots.map((slot) => [slot.id, slot])));
        }
      })
      .catch(() => {
        if (active) {
          setSlotWarning("Appointment details could not be loaded. Booking IDs are still shown.");
        }
      });
    return () => {
      active = false;
    };
  }, []);

  async function loadHistory(value) {
    const normalizedEmail = value.trim();
    if (!normalizedEmail) {
      setError("Enter the email address used for your booking.");
      return;
    }
    if (
      !initialBooking ||
      normalizedEmail.toLowerCase() !== initialBooking.email.toLowerCase()
    ) {
      setSelectedBooking(null);
    }

    setLoading(true);
    setError("");
    setNotice("");
    setPages([]);
    setPageIndex(0);
    setSearchedEmail(normalizedEmail);
    try {
      const firstPage = await getBookingHistory(normalizedEmail);
      setPages([firstPage]);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (initialBooking) {
      setSelectedBooking(initialBooking);
      setEmail(initialBooking.email);
      loadHistory(initialBooking.email);
    }
  }, [initialBooking]);

  const currentPage = pages[pageIndex];
  const currentBookings = currentPage?.bookings || [];
  const selectedIsVisible = currentBookings.some(
    (booking) => booking.id === selectedBooking?.id,
  );

  async function goNext() {
    if (!currentPage?.next_cursor || loading) return;
    if (pageIndex < pages.length - 1) {
      // Reuse fetched cursor pages rather than querying the same page again.
      setPageIndex(pageIndex + 1);
      return;
    }

    setLoading(true);
    setError("");
    try {
      const nextPage = await getBookingHistory(searchedEmail, {
        cursor: currentPage.next_cursor,
      });
      setPages((existing) => [...existing, nextPage]);
      setPageIndex((index) => index + 1);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  function goPrevious() {
    setPageIndex((index) => Math.max(0, index - 1));
  }

  async function confirmCancellation(bookingId) {
    setCancellingId(bookingId);
    setError("");
    setNotice("");
    try {
      const updatedBooking = await cancelBooking(bookingId);
      setPages((existing) =>
        existing.map((page) => ({
          ...page,
          bookings: page.bookings.map((booking) =>
            booking.id === bookingId ? updatedBooking : booking,
          ),
        })),
      );
      setSelectedBooking((current) =>
        current?.id === bookingId ? updatedBooking : current,
      );
      setPendingCancel("");
      setNotice("Appointment cancelled. Its time is now available to book again.");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setCancellingId("");
    }
  }

  function renderBooking(booking) {
    return (
      <BookingCard
        key={booking.id}
        booking={booking}
        slot={slotsById[booking.slot_id]}
        highlighted={booking.id === selectedBooking?.id}
        cancelling={cancellingId === booking.id}
        pendingCancel={pendingCancel === booking.id}
        onRequestCancel={() => setPendingCancel(booking.id)}
        onKeep={() => setPendingCancel("")}
        onConfirmCancel={() => confirmCancellation(booking.id)}
      />
    );
  }

  return (
    <section className="stack" aria-labelledby="page-title">
      <div>
        <p className="eyebrow">YOUR APPOINTMENTS</p>
        <h1 id="page-title" className="title">Booking History</h1>
        <p className="lead">Search by email to view or cancel your bookings.</p>
      </div>

      <form
        className="history-search"
        onSubmit={(event) => {
          event.preventDefault();
          loadHistory(email);
        }}
      >
        <div className="field">
          <label htmlFor="history-email">Email address</label>
          <input
            id="history-email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@example.com"
          />
        </div>
        <button className="button button-primary" type="submit" disabled={loading}>
          {loading ? "Loading…" : "Find bookings"}
        </button>
      </form>

      {error ? <p className="error-message" role="alert">{error}</p> : null}
      {notice ? <p className="notice-success" role="status">{notice}</p> : null}
      {slotWarning ? <p className="muted" role="status">{slotWarning}</p> : null}

      {selectedBooking && !selectedIsVisible ? (
        <div className="selected-booking">
          <p className="eyebrow">SELECTED BOOKING</p>
          {renderBooking(selectedBooking)}
        </div>
      ) : null}

      {currentPage && !loading ? (
        currentBookings.length > 0 ? (
          <>
            <div className="history-results">
              <p className="muted">
                Bookings for <strong>{searchedEmail}</strong>
              </p>
              <div className="booking-list">
                {currentBookings.map((booking) => renderBooking(booking))}
              </div>
            </div>
            <div className="pagination">
              <button
                className="button button-secondary"
                type="button"
                onClick={goPrevious}
                disabled={pageIndex === 0 || loading}
              >
                ← Previous
              </button>
              <span className="muted">Page {pageIndex + 1}</span>
              <button
                className="button button-secondary"
                type="button"
                onClick={goNext}
                disabled={!currentPage.next_cursor || loading}
              >
                Next →
              </button>
            </div>
          </>
        ) : (
          <div className="empty">
            <p><strong>No bookings found for this email.</strong></p>
            <p className="muted">Check the address or book an appointment to get started.</p>
          </div>
        )
      ) : null}
    </section>
  );
}
