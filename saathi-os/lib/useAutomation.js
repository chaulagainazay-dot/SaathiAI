"use client";
import { useEffect, useState } from "react";
import { fetchAutomation } from "./api";

// Live Automation Center status + Browser Health Score, polled.
export function useAutomation(intervalMs = 5000) {
  const [data, setData] = useState(null);
  const [live, setLive] = useState(false);

  useEffect(() => {
    let on = true;
    const tick = () =>
      fetchAutomation()
        .then((d) => { if (on) { setData(d); setLive(true); } })
        .catch(() => { if (on) setLive(false); });
    tick();
    const id = setInterval(tick, intervalMs);
    return () => { on = false; clearInterval(id); };
  }, [intervalMs]);

  return { data, live };
}
