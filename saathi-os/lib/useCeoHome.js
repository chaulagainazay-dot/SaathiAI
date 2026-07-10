// Live CEO Home data from the platform BFF. No mock fallback — honest empty states.
import { useEffect, useState } from "react";
import { fetchCeoHome } from "./api";

export function useCeoHome() {
  const [data, setData] = useState(null);
  const [live, setLive] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let on = true;
    setLoading(true);
    fetchCeoHome()
      .then((d) => {
        if (on) {
          setData(d || null);
          setLive(true);
        }
      })
      .catch(() => {
        if (on) setLive(false);
      })
      .finally(() => {
        if (on) setLoading(false);
      });
    return () => { on = false; };
  }, []);

  return { data, live, loading };
}
