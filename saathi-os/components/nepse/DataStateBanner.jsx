"use client";
// Visible data-quality state for a financial surface.
//
// This replaces a caption. A restart once turned 92 verified broker names into 8
// built-in ones and the only warning was a line of small grey text under a table —
// honest, but far too quiet for a screen someone reads money off. Fallback is a
// warning here; cached is a restrained notice that always carries its age; live
// says nothing at all, because the normal case should not shout.

export default function DataStateBanner({ banner, what = "reference data", detail = null }) {
  if (!banner || banner.severity === "none") return null;

  const warning = banner.severity === "warning";
  return (
    <div
      className="nepse-callout"
      role={warning ? "alert" : "status"}
      style={{
        marginTop: "0.75rem",
        borderLeftColor: warning ? "var(--gold)" : "var(--border)",
        background: warning ? "var(--gold-soft)" : "var(--surface-2)",
      }}
    >
      <strong>{banner.label}.</strong>{" "}
      {warning ? (
        <>
          Some {what} could not be verified for this session, so incomplete built-in
          values are standing in. Names and classifications below may be missing or
          wrong — check anything you act on.
        </>
      ) : (
        <>
          Showing the last verified {what}
          {banner.age ? <> from <span className="num">{banner.age}</span></> : null}. Not live.
        </>
      )}
      {banner.coverage && (
        <span style={{ color: "var(--text-faint)" }}> {banner.coverage}.</span>
      )}
      {detail && <div style={{ marginTop: "0.4rem", fontSize: "0.82rem" }}>{detail}</div>}
    </div>
  );
}
