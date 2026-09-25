import { redirect } from "next/navigation";

// Finance now lands on the unified, live Command Deck (browser, NEPSE, charts,
// Trading Guardian, and the agent-assisted Technical Analysis team).
// force-dynamic so redirect() issues a real server-side 307 (no static client-redirect flash).
export const dynamic = "force-dynamic";

export default function Finance() {
  redirect("/command-deck");
}
