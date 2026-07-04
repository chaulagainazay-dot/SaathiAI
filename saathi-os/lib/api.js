// Talks to the SaathiAI platform BFF (FastAPI, port 8765).
export const API_BASE =
  process.env.NEXT_PUBLIC_SAATHI_API || "http://localhost:8765";

export async function fetchCeoHome() {
  const r = await fetch(`${API_BASE}/api/executive/briefing`, { cache: "no-store" });
  if (!r.ok) throw new Error(`bff ${r.status}`);
  return r.json();
}
