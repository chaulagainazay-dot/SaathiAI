// Passkey (WebAuthn) client — fingerprint / Face ID unlock.
// The owner registers a platform authenticator once, then unlocks with biometrics.
import { API_BASE, afetch, setSessionToken } from "./api";

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
const post = (path, body) => afetch(`${API_BASE}${path}`, {
  method: "POST", credentials: "include",
  headers: body ? { "Content-Type": "application/json" } : {},
  body: body ? JSON.stringify(body) : undefined,
}).then((r) => r.json());

export function passkeySupported() {
  return typeof window !== "undefined" && !!window.PublicKeyCredential && !!navigator.credentials;
}

export function passkeyPlatformName() {
  if (typeof window === "undefined" || typeof navigator === "undefined") return "Biometrics";
  const ua = navigator.userAgent || "";
  const platform = navigator.platform || "";

  // iOS Face ID
  if (/iPhone|iPad/.test(ua) && /Safari/.test(ua) && !/Chrome/.test(ua)) return "Face ID";
  // macOS Touch ID
  if (/Mac/.test(platform) && !/iPhone|iPad/.test(ua)) {
    if (/Safari/.test(ua) || /Chrome/.test(ua)) return "Touch ID";
  }
  // Windows Hello
  if (/Win/.test(platform) && (/Edg/.test(ua) || /Chrome/.test(ua))) return "Windows Hello";
  // Android Biometrics
  if (/Android/.test(ua) && /Chrome/.test(ua)) return "fingerprint";
  // Fallback for iOS non-Safari
  if (/iPhone|iPad/.test(ua)) return "Face ID";

  return "Biometrics";
}

export function passkeyUnsupportedReason() {
  if (passkeySupported()) return null;
  return "This browser doesn't support passkeys. Use your password instead.";
}

export async function passkeyStatus() {
  const r = await afetch(`${API_BASE}/api/v1/auth/passkey/status`, { cache: "no-store" });
  return r.json();   // { has_passkey, rp_id, signed_in }
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
export async function unlockPasskey(rememberMe = true) {
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
  const body = { credential: payload };
  if (rememberMe !== undefined) body.remember_me = rememberMe;
  const res = await post("/api/v1/auth/passkey/login/verify", body);
  if (res && res.token) setSessionToken(res.token);
  return res;
}

// Diagnostic helper — maps WebAuthn errors to human-readable messages.
export async function diagnosePasskeyError(errorName, reason = "") {
  try {
    const { fetchPasskeyDiagnostics } = await import("./api");
    const j = await fetchPasskeyDiagnostics(errorName, reason);
    return j.message || "Passkey error. Please try again or use your password.";
  } catch {
    // Fallback messages if the backend endpoint is unreachable
    const map = {
      NotAllowedError: "You cancelled the passkey prompt. You can try again or use your password.",
      NotSupportedError: "This browser doesn't support passkeys. Try Safari, Chrome, or Edge.",
      SecurityError: "Passkeys require a secure context (HTTPS or localhost).",
      InvalidStateError: "A passkey already exists for this device. Try unlocking instead.",
      AbortError: "The passkey request was interrupted. Please try again.",
    };
    return map[errorName] || `Passkey error (${errorName}). Please try again or use your password.`;
  }
}
