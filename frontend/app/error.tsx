"use client";

import Link from "next/link";
import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Archive page error:", error);
  }, [error]);

  return (
    <div className="stack">
      <section className="noticePanel">
        <p className="eyebrow">Error</p>
        <h1>Something went wrong</h1>
        <p>
          An unexpected error occurred while loading this page. This may be a
          temporary issue with the archive backend.
        </p>
        {error.digest ? (
          <p style={{ color: "var(--muted)", fontSize: "0.88rem" }}>
            Error ID: <code>{error.digest}</code>
          </p>
        ) : null}
        <div style={{ display: "flex", gap: 12, marginTop: 18, flexWrap: "wrap" }}>
          <button className="primaryLink" onClick={reset} type="button">
            Try again
          </button>
          <Link className="secondaryLink" href="/">
            Return home
          </Link>
        </div>
      </section>
    </div>
  );
}
