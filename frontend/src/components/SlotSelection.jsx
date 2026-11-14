import React, { useEffect, useMemo, useState } from "react";

import { dateKey, formatDateShort, formatTime } from "../format.js";

export default function SlotSelection({ slots, loading, error, onRetry, onSelect }) {
  const upcoming = useMemo(
    () =>
      slots
        .filter((slot) => slot.available && new Date(slot.start) > new Date())
        .sort((a, b) => new Date(a.start) - new Date(b.start)),
    [slots],
  );
  const providers = useMemo(
    () => [...new Set(upcoming.map((slot) => slot.provider))].sort((a, b) => a.localeCompare(b)),
    [upcoming],
  );
  const dates = useMemo(
    () => [...new Set(upcoming.map((slot) => dateKey(slot.start)))],
    [upcoming],
  );
  const [provider, setProvider] = useState("all");
  const [selectedDate, setSelectedDate] = useState("");

  useEffect(() => {
    if (!dates.includes(selectedDate)) {
      setSelectedDate(dates[0] || "");
    }
  }, [dates, selectedDate]);

  const visibleSlots = upcoming.filter(
    (slot) =>
      dateKey(slot.start) === selectedDate &&
      (provider === "all" || slot.provider === provider),
  );

  return (
    <section className="stack" aria-labelledby="page-title">
      <div>
        <p className="eyebrow">BOOK AN APPOINTMENT</p>
        <h1 id="page-title" className="title">
          Choose a time that works for you.
        </h1>
        <p className="lead">Select a provider and date to see open appointments.</p>
      </div>

      <div>
        <p className="eyebrow" id="provider-label">PROVIDER</p>
        <div className="pills" role="group" aria-labelledby="provider-label">
          <button
            type="button"
            className="pill"
            aria-pressed={provider === "all"}
            onClick={() => setProvider("all")}
          >
            All Providers
          </button>
          {providers.map((name) => (
            <button
              type="button"
              className="pill"
              aria-pressed={provider === name}
              key={name}
              onClick={() => setProvider(name)}
            >
              {name}
            </button>
          ))}
        </div>
      </div>

      <div>
        <p className="eyebrow" id="date-label">DATE</p>
        {dates.length > 0 ? (
          <div className="date-strip" role="group" aria-labelledby="date-label">
            {dates.map((key) => {
              const date = new Date(`${key}T12:00:00`);
              return (
                <button
                  type="button"
                  className="date-button"
                  aria-pressed={selectedDate === key}
                  key={key}
                  onClick={() => setSelectedDate(key)}
                >
                  {formatDateShort(date)}
                </button>
              );
            })}
          </div>
        ) : null}
      </div>

      <div className="results-line" role="status">
        <p>
          <strong>{visibleSlots.length}</strong>{" "}
          {visibleSlots.length === 1 ? "appointment" : "appointments"} available
        </p>
        <p className="muted">
          {selectedDate
            ? new Date(`${selectedDate}T12:00:00`).toLocaleDateString(undefined, {
                weekday: "long",
                day: "numeric",
                month: "long",
              })
            : "Upcoming appointments"}
        </p>
      </div>

      {loading ? <p className="muted" role="status">Loading available appointments…</p> : null}
      {error ? (
        <div className="notice" role="alert">
          <p>{error}</p>
          <button className="text-button" onClick={onRetry} type="button">
            Try again
          </button>
        </div>
      ) : null}
      {!loading && !error && visibleSlots.length === 0 ? (
        <div className="empty">
          <p><strong>No open appointments for this selection.</strong></p>
          <p className="muted">Try another date or provider.</p>
        </div>
      ) : null}
      {!loading && !error && visibleSlots.length > 0 ? (
        <div className="slot-grid" aria-label="Available appointments">
          {visibleSlots.map((slot) => (
            <button
              className="slot"
              key={slot.id}
              onClick={() => onSelect(slot)}
              type="button"
              aria-label={`${formatTime(slot.start)} with ${slot.provider}`}
            >
              <span className="slot-time">{formatTime(slot.start)}</span>
              <span className="slot-provider">{slot.provider}</span>
            </button>
          ))}
        </div>
      ) : null}
    </section>
  );
}