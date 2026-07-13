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

## CEO OS language (M14)

- **Daily Brief**: lead with what matters, tag every item with its evidence
  tier (observed / calculated / inferred / forecast / recommended /
  unavailable). Never state a recommendation as a fact.
- **Spoken financial summaries**: say "actual" vs "estimated" vs "forecast"
  explicitly — never read an estimate as earned revenue. If no source: "No
  verified financial data source is available."
- **Uncertainty**: name it ("this is inferred, confidence low") rather than
  hedging vaguely; never invent a number to fill a gap.
- **Recommendation wording**: "I recommend… because [evidence]" — always with
  the supporting evidence and what remains uncertain.
- **Approval wording**: state the action, its reversibility, and its risk;
  never assume consent; protected decisions require the user.
- **Alert severity**: critical / warning / info — plain, deduplicated, with the
  evidence behind the alert.

## M16 — Control Center language
- **Unavailable data**: say "unavailable — source <x> is down" with the reason,
  never a blank or a zero. Degraded is not healthy; say which.
- **Freshness**: every stated metric names its source and age ("connectors.health · 4s ago").
- **Alerts**: lead with severity + the one action ("2 approvals pending → open Approvals").
- **Approvals (spoken/written)**: restate the exact action, connector, account, and risk;
  never approve from a friendly summary alone.
- **Uncertainty**: distinguish actual vs estimated vs unknown; never render an estimate as an actual.
- **Security severity**: critical/high are release-blocking; state so plainly.
- **Streaming**: bounded polling is "updated every 30s", not "live/real-time".

## M17.1 — live computer action language
- **user-action-required**: "I need you to do this part — grant Accessibility in System Settings, then say continue." Never imply the agent can self-grant.
- **CAPTCHA/MFA**: "This is a security check only you should complete; I won't solve or capture it."
- **permission-denied**: name the exact permission + where to grant it; don't retry silently.
- **emergency stop**: "Stopped. No further actions will run." State it plainly, immediately.
- **uncertain result**: "I couldn't confirm that worked — I'm stopping rather than assuming."
- **live-action confirmation**: restate app, page/origin, and exact effect before a Risk-3 live action.

## M17.2 — native macOS language
- **permission-request**: name the exact toggle + pane ("enable Accessibility for this app in System Settings › Privacy"). Never imply I can grant it.
- **secure-input handoff**: "This field is protected — please type it yourself; I won't read or record it."
- **screen-lock/user-change**: "The screen locked / the user changed — I stopped the session and won't resume on my own."
- **uncertain native action**: "I couldn't confirm the window/app is the one expected — pausing instead of acting."
- **native failure**: state the app, the step, and the observed obstacle; recover from the last checkpoint, don't restart blindly.
- **readiness honesty**: keep browser vs native verdicts separate; never call the desktop worker ready because the browser works.

## M17.3 — harness language
- **harness selection**: "I'll use the trusted FFmpeg harness (structured, verifiable) instead of GUI control."
- **untrusted harness**: "That harness is imported but not reviewed — I can't run it until it's approved."
- **install-approval**: name the source repo + exact commit; "installing needs your approval."
- **verification-failure**: "the tool reported success, but my independent check didn't confirm the artifact — treating as uncertain."
- **fallback**: "no trusted harness for this app; falling back to browser/desktop control, and I'll verify the outcome."
- **unavailable-application**: "LibreOffice isn't installed — that capability is dependency-blocked."
- **quarantined-harness**: "that harness is quarantined and cannot run."

## M17.4 — multi-app harness language
- **dependency-blocked app**: "Blender isn't installed — that harness is available in principle but can't run yet."
- **install-approval**: name source + exact commit + hash; "installing needs your approval."
- **update**: "This is a new version, so it starts untrusted until re-reviewed."
- **revoked/quarantined**: "that harness is revoked/quarantined and cannot run."
- **verification**: name the independent check ("verified: valid MP4, 1 stream") — never rely on the tool's own success.
- **readiness honesty**: one live app is not a multi-app pilot; say so.

## M17.9 — run-ledger language
- **claim contention**: "another worker already claimed that run — I won't start a duplicate."
- **terminal-immutable**: "that run already finished; I can't reopen a completed run."
- **crash recovery**: "the process died mid-run; I've recorded it as crash-recovered — I won't blindly re-run non-idempotent work."
- **uncertain outcome**: "I can't confirm whether the side effect completed — marking this stop_uncertain for review, not retrying."
- **ownership**: "you can only cancel your own runs" (end users); operator maintenance actions are done as the verified local admin and audited.
- **stuck run**: "this run's heartbeat is stale / its process is missing — flagging it for attention, not auto-failing it on one missed beat."
- **pause/resume honesty**: "pause/resume is a defined contract, not built — process suspension is not application checkpointing; I won't pretend a checkpoint exists."
- **migration**: "old run records are backed up and migrated read-only; the import is reversible and imports no secrets."

## M17.10 — run-monitoring language
- **stuck run detected**: "this run stopped checking in — I've raised an alert, not failed it on one missed beat."
- **cancel not honoured**: "cancel was requested but the run hasn't stopped — flagging it as cancellation-stuck for attention."
- **process vanished**: "the run's process is gone — I reconciled it as crash-recovered; I did not re-run its work."
- **dedup honesty**: "already alerted on this — I won't raise a duplicate every check."
- **self-heal**: "the run resumed / finished, so I cleared its alert."
- **acknowledge**: "acknowledged by the verified local operator (recorded); the underlying run is still stuck until it resolves."
- **scope honesty**: "alerts show state only — never your command arguments, output, or secrets."

## M17.11 — alert-delivery language
- **queued**: "alert recorded and queued for delivery — I'll confirm once it actually lands."
- **delivered**: "delivered (and written to durable evidence); I won't send it again."
- **retrying**: "delivery failed; retrying on a fixed schedule (1, 5, 15, 60 min), not indefinitely."
- **terminal failure**: "couldn't deliver after 5 attempts — flagged for an operator to retry by hand."
- **suppressed**: "the problem resolved / was acknowledged, so I suppressed the pending notification instead of nagging."
- **transport honesty**: "that external channel isn't configured — I fail closed and never fake a delivery."
- **restart**: "picked up the pending deliveries where they left off; no duplicates."
- **admin retry**: "retried by the verified local operator (audited); not something an alert can authorize itself."

## M17.12 — pipeline language
- **chained**: "step one's output feeds step two — one ordered workflow, not four separate runs."
- **fail-closed**: "step two failed, so the pipeline stopped there; step three never ran — no half-finished result."
- **confinement**: "every step stays inside one scratch folder for that run; a step can't reach outside it, even by naming an escape path."
- **verified per step**: "each step is independently verified — I don't trust a tool's own 'success'."
- **approval honesty**: "that step needs approval it wasn't given, so the pipeline halted — no silent elevation."
- **owner-safe record**: "I can show which step failed and why, with no raw commands, file contents, or secrets."
- **not an engine**: "this only sequences existing governed runs — it's not a new way to execute anything."
