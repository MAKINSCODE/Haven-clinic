import React from "react";

export default function LandingPage({ onBook, onGetBooking, onBookingHistory }) {
  return (
    <section aria-labelledby="page-title" className="landing">
      <p className="eyebrow">HAVEN CLINIC</p>
      <h1 id="page-title" className="display">
        Care that fits your day.
      </h1>
      <p className="lead">
        Choose a doctor, pick a time and book an appointment in under a minute.
      </p>
      <div className="action-row">
        <button className="button button-primary" onClick={onBook} type="button">
          Book an Appointment <span aria-hidden="true">→</span>
        </button>
        <button className="button button-secondary" onClick={onGetBooking} type="button">
          Find booking
        </button>
        <button className="button button-secondary" onClick={onBookingHistory} type="button">
          Booking History
        </button>
      </div>
      <div className="mission">
        <p className="eyebrow">OUR MISSION</p>
        <p className="mission-copy">Providing thoughtful, accessible care.</p>
      </div>
    </section>
  );
}