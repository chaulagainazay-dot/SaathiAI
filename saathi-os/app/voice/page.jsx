import { redirect } from "next/navigation";

// R2.1-S6 — the speaker-enrollment surface is retired.
//
// This page used to record ~5 seconds of the owner's voice and post it to
// /api/v1/voice/enroll under the claim that a voice profile "unlocks owner
// actions". It never did, and after the authority repair it cannot: a
// voiceprint is an observation, not a credential. The capability is retired
// rather than re-gated, so the surface that advertised it is gone too.
//
// Deliberately a server component with no "use client", no state, and no
// imports from lib/api or the media APIs: the redirect resolves before any
// browser code runs, so navigating here can never open a microphone.
//
// Voice settings live at /settings/voice (output preferences and capture
// constraints, no enrollment). Per-Mission Voice Studio is reached through
// /missions → a mission dashboard → its Voice link; the mission list is not
// duplicated here.
export default function RetiredVoiceHub() {
  redirect("/settings/voice");
}
