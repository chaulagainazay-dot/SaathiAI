import { redirect } from "next/navigation";

// Folded into the unified Command Deck (Chart Analysis / NEPSE Tracker / Financial Browser
// now live there). force-dynamic so this is a real server redirect.
export const dynamic = "force-dynamic";

export default function Page() {
  redirect("/command-deck");
}
