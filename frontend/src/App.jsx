import React, { useCallback, useEffect, useState } from "react";

import { createBooking, getSlots } from "./api.js";
import BookingForm from "./components/BookingForm.jsx";
import Confirmation from "./components/Confirmation.jsx";
import FindBooking from "./components/FindBooking.jsx";
import Header from "./components/Header.jsx";
import LandingPage from "./components/LandingPage.jsx";
import MyBookings from "./components/MyBookings.jsx";
import SlotSelection from "./components/SlotSelection.jsx";

export default function App() {
  const [screen, setScreen] = useState("home");
  const [slots, setSlots] = useState([]);
  const [slotsLoading, setSlotsLoading] = useState(false);
  const [slotsError, setSlotsError] = useState("");
  const [slotsVersion, setSlotsVersion] = useState(0);
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [booking, setBooking] = useState(null);
  const [bookingSlot, setBookingSlot] = useState(null);
  const [lookupBookingId, setLookupBookingId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");

  const refreshSlots = useCallback(() => {
    setSlotsVersion((version) => version + 1);
  }, []);

  useEffect(() => {
    if (screen !== "select") return undefined;
    let active = true;
    setSlotsLoading(true);
    setSlotsError("");
    getSlots()
      .then((result) => {
        if (active) setSlots(result);
      })
      .catch((error) => {
        if (active) setSlotsError(error.message);
      })
      .finally(() => {
        if (active) setSlotsLoading(false);
      });
    return () => {
      active = false;
    };
  }, [screen, slotsVersion]);

  function openBooking() {
    setScreen("select");
    setSubmitError("");
  }

  async function confirmBooking({ name, email, idempotencyKey }) {
    setSubmitting(true);
    setSubmitError("");
    try {
      const created = await createBooking(
        { slot_id: selectedSlot.id, name, email },
        idempotencyKey,
      );
      setBooking(created);
      setBookingSlot(selectedSlot);
      setSlots((available) => available.filter((slot) => slot.id !== selectedSlot.id));
      setScreen("confirmed");
    } catch (error) {
      setSubmitError(error.message);
    } finally {
      setSubmitting(false);
    }
  }

  function viewBooking() {
    setLookupBookingId(booking.id);
    setScreen("lookup");
  }

  function openHistory() {
    setScreen("history");
  }

  function openBookingLookup(bookingId = "") {
    setLookupBookingId(bookingId);
    setScreen("lookup");
  }

  function bookAnother() {
    setSelectedSlot(null);
    setBooking(null);
    setBookingSlot(null);
    setLookupBookingId("");
    setScreen("select");
    refreshSlots();
  }

  let content;
  if (screen === "select") {
    content = (
      <SlotSelection
        slots={slots}
        loading={slotsLoading}
        error={slotsError}
        onRetry={refreshSlots}
        onSelect={(slot) => {
          setSelectedSlot(slot);
          setSubmitError("");
          setScreen("form");
        }}
      />
    );
  } else if (screen === "form" && selectedSlot) {
    content = (
      <BookingForm
        slot={selectedSlot}
        submitting={submitting}
        error={submitError}
        onBack={() => setScreen("select")}
        onConfirm={confirmBooking}
      />
    );
  } else if (screen === "confirmed" && booking && bookingSlot) {
    content = (
      <Confirmation
        booking={booking}
        slot={bookingSlot}
        onViewBooking={viewBooking}
        onBookAnother={bookAnother}
      />
    );
  } else if (screen === "lookup") {
    content = <FindBooking initialBookingId={lookupBookingId} />;
  } else if (screen === "history") {
    content = <MyBookings />;
  } else {
    content = (
      <LandingPage
        onBook={openBooking}
        onGetBooking={() => openBookingLookup()}
        onBookingHistory={openHistory}
      />
    );
  }

  return (
    <div className="app-shell">
      <Header
        screen={screen}
        onHome={() => setScreen("home")}
        onBook={openBooking}
        onGetBooking={() => openBookingLookup()}
        onBookingHistory={openHistory}
      />
      <main className="page-content">{content}</main>
      <footer className="site-footer">
        <span>HAVEN CLINIC</span>
        <span>Thoughtful care, made simple.</span>
      </footer>
    </div>
  );
}