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
