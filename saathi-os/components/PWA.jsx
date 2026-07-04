"use client";
import { useEffect } from "react";

// Registers the service worker (offline) and is a no-op during dev SSR.
export default function PWA() {
  useEffect(() => {
    if ("serviceWorker" in navigator && process.env.NODE_ENV === "production") {
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    }
  }, []);
  return null;
}
