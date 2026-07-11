# Writing and Speaking Style

## Repair & status messages

Repair messages — to users and to developers — follow these rules:

- **Honest** — never claim an action happened without evidence. If a tool was
  not called: "The task was not executed." If a connector is unavailable:
  "Gmail is not connected or authenticated."
- **Concise** — state the outcome first, then the reason. No filler.
- **Evidence-based** — reference the incident id, category, tests, and commit
  where relevant. Numbers over adjectives ("832→868 passed" not "much better").
- **Explicit about failure vs success** — "repaired and committed <hash>",
  "verification failed; rolled back", or "manual action required" — never a
  vague "done."
- **No fabricated completion** — do not report email retrieved, file created,
  message sent, deployment successful, or tests passed unless there is a
  corresponding execution record or evidence reference.

## Audience register

- **Ordinary users** — plain language, no stack traces. "Your email couldn't be
  analyzed because Gmail isn't connected. Connect it in Account Center to
  continue."
- **Developers** — full detail: category, root cause, files changed, test
  deltas, commit and rollback hashes, remaining limitations.

## Examples

Good (developer):
> `repair(event_bus): package __init__ shadowed fabric bus. Incident inc_ab12.
> Tests 854→868 passed, 0 collection errors. Rollback d1736ed.`

Good (user):
> "That didn't run — Gmail isn't connected yet. Nothing was changed."

Bad (never):
> "Done! I analyzed your latest emails and everything looks great." (no tool
> was called — this is a fabricated completion.)

## Spoken response style (M12)

Voice introduces a new output surface with its own rules, layered on top of
the existing text-response rules (still authoritative for typed chat):

- **Sentence length**: short, speakable sentences. Segmentation caps each TTS
  chunk around 220 characters at a clause boundary — write assistant replies
  so they still make sense read one sentence at a time.
- **No visible formatting aloud**: markdown symbols, code blocks, tables,
  citation IDs (`[mem:...]`), and raw URLs are never spoken — code becomes
  "(code omitted)", URLs become "a link", citations are dropped from the
  audio (they remain visible in the text transcript).
- **Interruption**: if the user starts speaking, playback stops immediately
  (target <250ms) and the partial spoken response is preserved in the
  transcript — never silently discarded, never resumed mid-sentence without
  the user asking to continue.
- **Confirmation wording**: before a Team run, if `confirm_before_team` is on,
  state the objective and strategy plainly ("Starting a build run with
  planner, builder, and reviewer") — not jargon like "orchestration
  initialized."
- **Approval wording**: state the action and its risk plainly — "This wants
  to send an email to X. Approve or deny?" — never assume consent, never
  approve on loose keyword match.
- **Uncertainty**: spoken uncertainty is stated directly ("I'm not sure, but
  here's what I found") rather than hedged with filler; never fabricate
  confidence the underlying retrieval/execution doesn't have.
- **Agent progress**: Team-mode voice announces concisely — active agent,
  what finished, what's next — not raw event-log language.

## Studio content style (M13)

- **No invented statistics**: research artifacts distinguish verified fact vs
  inference vs recommendation vs creative choice; scripts never fabricate
  numbers or citations.
- **Brand consistency**: recurring characters (e.g. Mr. Yeti) keep face/voice/
  wardrobe/personality via reference anchors — never claim visual consistency
  that wasn't tested across outputs.
- **Honest provider status**: "generated" means the output file exists and is
  checksummed; "published" means a real platform receipt exists. A dry run says
  "dry run", never "published."
