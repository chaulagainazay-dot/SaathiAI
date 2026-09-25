// SaathiOS Browser — the app's side of the governed browser.
//
// This route adds NO authority. It validates the request, forwards the caller's
// session to the backend, and returns what the governed browser allowed. Every
// decision that matters — domain policy, the deny list, risk, approval, the
// execution ledger — happens behind /api/v1/browser/fetch, and this file must
// never grow a path that reaches the network directly.
//
// It is auth-forwarded on purpose. An unauthenticated endpoint that fetches
// arbitrary URLs server-side is a server-side request forgery proxy, whatever the
// allowlist says.

import { NextResponse } from "next/server";
import { validateUrl, checkAction } from "@/lib/browser/result";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const BACKEND = process.env.SAATHI_API_BASE || "http://127.0.0.1:8765";
const TIMEOUT_MS = 70_000;
const MAX_SELECTOR = 200;

const fail = (reason, extra = {}, status = 200) =>
  NextResponse.json({ ok: false, reason, ...extra },
    { status, headers: { "cache-control": "no-store" } });

export async function POST(request) {
  let body;
  try {
    body = await request.json();
  } catch {
    return fail("BAD_JSON", {}, 400);
  }

  const url = validateUrl(body?.url);
  if (!url.ok) return fail(url.reason, { message: url.message }, 400);

  const action = checkAction(body?.action || "read");
  if (!action.ok) return fail(action.reason, { message: action.message }, 400);

  const selector = String(body?.selector || "").slice(0, MAX_SELECTOR);

  // Forward the caller's identity; never mint one here.
  const headers = { "content-type": "application/json" };
  const cookie = request.headers.get("cookie");
  const bearer = request.headers.get("authorization");
  if (cookie) headers.cookie = cookie;
  if (bearer) headers.authorization = bearer;

  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${BACKEND}/api/v1/browser/fetch`, {
      method: "POST",
      headers,
      signal: ac.signal,
      cache: "no-store",
      body: JSON.stringify({
        url: url.url,
        action: action.action,
        selector,
        timeout: 30,
        actor: "user:saathios-browser",
      }),
    });
    if (!res.ok) return fail(`BACKEND_${res.status}`, { governed: true });
    const data = await res.json();
    return NextResponse.json(data, { headers: { "cache-control": "no-store" } });
  } catch (e) {
    const aborted = e?.name === "AbortError";
    return fail(aborted ? "TIMEOUT" : "BACKEND_UNREACHABLE", {
      message: aborted
        ? "The page did not come back in time."
        : "The governed browser is not running. Start the SaathiAI backend.",
    });
  } finally {
    clearTimeout(timer);
  }
}
