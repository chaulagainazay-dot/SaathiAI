"use client";

/**
 * Identity of the central Command Core interaction.
 *
 * SaathiOS already correlates agent runs by `conversation_id`; the /command
 * surface simply had no conversation of its own, which is why it could never
 * resolve a run in context. This gives it one, per browser tab, so runs started
 * from the centre are correlated the same way chat's runs already are.
 *
 * It is an identifier, not a credential and not a claim about runtime state:
 * it grants nothing and is never used for authentication or authority.
 */

const KEY = "saathi_command_conversation";

export function commandConversationId() {
  if (typeof window === "undefined") return "";
  try {
    const existing = window.sessionStorage.getItem(KEY);
    if (existing) return existing;
    const id = `cmd-${(crypto?.randomUUID?.() || Math.random().toString(36).slice(2)).replace(/-/g, "").slice(0, 24)}`;
    window.sessionStorage.setItem(KEY, id);
    return id;
  } catch {
    // Private mode or blocked storage: the centre simply has no contextual run,
    // which is a truthful outcome rather than a fabricated one.
    return "";
  }
}
