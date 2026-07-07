// Passkey (WebAuthn) client — fingerprint / Face ID unlock.
// The owner registers a platform authenticator once, then unlocks with biometrics.
import { API_BASE } from "./api";

const b64uToBuf = (s) => {
  s = s.replace(/-/g, "+").replace(/_/g, "/");
  s += "=".repeat((4 - (s.length % 4)) % 4);
  const bin = atob(s);
  const buf = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
  return buf.buffer;
};
const bufToB64u = (buf) => {
  const bytes = new Uint8Array(buf);
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
};
const post = (path, body) => fetch(`${API_BASE}${path}`, {
  method: "POST", credentials: "include",
  headers: body ? { "Content-Type": "application/json" } : {},
  body: body ? JSON.stringify(body) : undefined,
}).then((r) => r.json());

export function passkeySupported() {
  return typeof window !== "undefined" && !!window.PublicKeyCredential && !!navigator.credentials;
}

export async function passkeyStatus() {
  const r = await fetch(`${API_BASE}/api/v1/auth/passkey/status`, { cache: "no-store" });
  return r.json();   // { has_passkey, rp_id }
}

// Register a new passkey (must already be signed in). Prompts Touch ID / Face ID.
export async function registerPasskey() {
  const opts = await post("/api/v1/auth/passkey/register/options");
  if (opts.error) throw new Error(opts.error);
  opts.challenge = b64uToBuf(opts.challenge);
  opts.user.id = b64uToBuf(opts.user.id);
  (opts.excludeCredentials || []).forEach((c) => (c.id = b64uToBuf(c.id)));
  const cred = await navigator.credentials.create({ publicKey: opts });
  const payload = {
    id: cred.id, rawId: bufToB64u(cred.rawId), type: cred.type,
    response: {
      clientDataJSON: bufToB64u(cred.response.clientDataJSON),
      attestationObject: bufToB64u(cred.response.attestationObject),
    },
  };
  return post("/api/v1/auth/passkey/register/verify", { credential: payload });
}

// Unlock with biometrics → sets the owner session.
export async function unlockPasskey() {
  const opts = await post("/api/v1/auth/passkey/login/options");
  if (opts.error) throw new Error(opts.error);
  opts.challenge = b64uToBuf(opts.challenge);
  (opts.allowCredentials || []).forEach((c) => (c.id = b64uToBuf(c.id)));
  const a = await navigator.credentials.get({ publicKey: opts });
  const payload = {
    id: a.id, rawId: bufToB64u(a.rawId), type: a.type,
    response: {
      clientDataJSON: bufToB64u(a.response.clientDataJSON),
      authenticatorData: bufToB64u(a.response.authenticatorData),
      signature: bufToB64u(a.response.signature),
      userHandle: a.response.userHandle ? bufToB64u(a.response.userHandle) : null,
    },
  };
  return post("/api/v1/auth/passkey/login/verify", { credential: payload });
}
