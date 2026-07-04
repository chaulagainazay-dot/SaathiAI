"use client";
import { useEffect, useState } from "react";
import { home as mock } from "./data";
import { fetchCeoHome } from "./api";

// Live CEO Home data from the platform BFF, with graceful offline fallback to
// the mock contract (so the companion still works with no connection).
export function useCeoHome() {
  const [data, setData] = useState(mock);
  const [live, setLive] = useState(false);

  useEffect(() => {
    let on = true;
    fetchCeoHome()
      .then((d) => { if (on) { setData({ ...mock, ...d }); setLive(true); } })
      .catch(() => { if (on) setLive(false); });
    return () => { on = false; };
  }, []);

  return { data, live };
}
