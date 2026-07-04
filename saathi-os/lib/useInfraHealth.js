"use client";
import { useEffect, useState } from "react";
import { fetchInfraHealth } from "./api";

// Live infrastructure health, polled. The "engine warning light" for the CEO.
export function useInfraHealth(intervalMs = 20000) {
  const [data, setData] = useState(null);
  const [live, setLive] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let on = true;
    const tick = () =>
      fetchInfraHealth()
        .then((d) => { if (on) { setData(d); setLive(true); setError(null); } })
        .catch((e) => { if (on) { setLive(false); setError(e.message); } });
    tick();
    const id = setInterval(tick, intervalMs);
    return () => { on = false; clearInterval(id); };
  }, [intervalMs]);

  return { data, live, error };
}
