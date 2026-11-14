import React from "react";

export default function Header({ screen, onHome, onBook, onBookings }) {
  const bookingActive = ["select", "form", "confirmed"].includes(screen);
  return (
    <header className="site-header">
      <button className="brand" type="button" onClick={onHome} aria-label="Haven Clinic home">
        <span className="brand-mark" aria-hidden="true">H</span>
        <span>haven clinic</span>
      </button>
      <nav className="main-nav" aria-label="Main navigation">
        <button
          type="button"
          className={bookingActive ? "nav-link active" : "nav-link"}
          aria-current={bookingActive ? "page" : undefined}
          onClick={onBook}
        >
          Book an Appointment
        </button>
        <button
          type="button"
          className={screen === "history" ? "nav-link active" : "nav-link"}
          aria-current={screen === "history" ? "page" : undefined}
          onClick={onBookings}
        >
          My Bookings
        </button>
      </nav>
    </header>
  );
}
