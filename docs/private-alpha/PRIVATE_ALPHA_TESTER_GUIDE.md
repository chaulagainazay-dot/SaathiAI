# SaathiOS Private Alpha — Tester Guide

Thank you for testing SaathiOS. This guide tells you what it is, what it will
not do, how to report what you find, and what to do when something breaks.

Read [`PRIVATE_ALPHA_SCOPE.md`](PRIVATE_ALPHA_SCOPE.md) before you start. It sets
the expectations this guide assumes.

---

## What you are testing

SaathiOS private alpha runs **entirely on one machine** — the one it was
installed on. It is reachable only at `http://localhost:3000`. There is no public
URL, and nothing you do leaves that machine.

You are here by invitation. There is no sign-up page, and there will not be one
during the alpha.

## What it will not do

It is worth being blunt about this, because some of it may look like a bug:

- **It will not connect to a broker, exchange, or any trading account.** It never
  asks for a trading credential, and it will never accept one.
- **It will not place, change, or cancel an order.** Not live, not paper, not
  simulated-through-a-real-provider.
- **It will not read your balances or positions.** There is nothing connected to
  read them from.
- **It will not approve its own work.** Anything that changes state needs a
  person to approve it. That person is not the assistant.
- **It will not run unattended forever.** There is no uptime guarantee. Expect
  restarts.

If you ever see something that looks like it is connecting to a broker, reading
an account, or executing a trade — **stop and report it immediately as a SEV1**.
That would be a serious defect, not a feature.

## Never enter a real credential

SaathiOS private alpha never asks you for an API key, a broker login, an OAuth
authorization, or a payment method. If any screen appears to ask for one:

1. Do not enter it.
2. Screenshot the screen.
3. Report it as SEV1.

If you already entered a real credential somewhere in the product, tell us
immediately **and rotate that credential at its source.** Assume it is
compromised.

## Getting started

1. Open the invitation link you were sent. It works once.
2. Set your password. It must be reasonably strong; the form will tell you if it
   is not.
3. You will land in one organization and one workspace. That is the only one you
   can see, by design.
4. Follow the first-run onboarding.

If your link says the invitation is no longer pending, it has already been used —
ask for a new one rather than trying it again.

## The core loop to exercise

1. Create a project.
2. Create a mission in it.
3. Watch it get validated.
4. When it asks for approval, notice that it **stops and waits**.
5. Have the owner approve it (or, if you are the owner, approve it yourself —
   but note you cannot approve a mission you requested).
6. Watch it run, and watch progress update.
7. Look at the evidence and the audit trail afterwards.
8. Cancel a mission mid-run and confirm it stops cleanly.
9. Sign out and back in.

Please try to break each of these. Especially step 4 — if you can get a mission
to run without a human approving it, that is the single most valuable bug you
can find.

## Reporting an issue

Use this format. It takes two minutes and saves an hour.

```
TITLE:        one line, what broke
SEVERITY:     SEV1 / SEV2 / SEV3   (see below)
WHEN:         date and time, with your timezone
WHAT I DID:   numbered steps, starting from sign-in
EXPECTED:     what you thought would happen
HAPPENED:     what actually happened
SCREENSHOTS:  attached (see below)
MISSION ID:   if applicable
APPROVAL ID:  if applicable
ERROR CODE:   the code shown on screen, verbatim
```

### Severity

- **SEV1** — a safety boundary broke. Something ran without approval; you saw
  another person's data; it asked for a credential; it looked like it contacted
  a broker; a session kept working after being revoked. **Report immediately, and
  stop using the system until you hear back.**
- **SEV2** — data or evidence looks wrong. Work disappeared, the audit trail is
  missing something you did, a backup failed.
- **SEV3** — everything else. Confusing wording, a slow page, an empty state that
  should not be empty, a mission that failed for an unclear reason.

When in doubt, pick the higher severity. We would much rather triage down.

### Screenshots to include

- The screen where it went wrong, **full window** — not a crop. The status bar at
  the bottom carries the local platform status, which is often the clue.
- The error message, if there is one, with the error code readable.
- For a mission problem: the mission page and its evidence panel.
- For an approval problem: the approval, showing who requested and who decided.

### Collecting logs

```bash
bin/saathi-alpha support-bundle
```

This writes a support bundle and runs a privacy scan over it before handing it to
you. Attach the bundle path in your report.

If you prefer to grab logs by hand, they are under `~/.saathi/logs/`.

### Redaction — please check before sending

The support bundle scans for secrets, but it cannot know what is private to
**you**. Before attaching anything, check for and remove:

- your email address, if you would rather not share it,
- any real names, client names or business data you put into a mission,
- anything in a screenshot's background — other windows, browser tabs, notifications.

Never send: a password, a session token, an API key of any kind, or a recovery
code. We will never ask you for one, and there is no situation in this alpha
where we need one.

## Reproduction steps

The most useful report is one we can reproduce. If you can, try it twice:

1. Sign out, sign back in, and try the exact same steps.
2. Tell us whether it happened both times, or only once.

An intermittent bug is still worth reporting — just say that it was
intermittent, because that changes how we look for it.

## Known limitations

These are expected. Please do not file them as bugs unless the behaviour differs
from what is described here.

- Single machine, localhost only. No access from your phone or another computer.
- Invite only. No sign-up.
- No broker connectivity, no market data, no trading of any kind.
- Missions run local, deterministic tools and mock providers only.
- Approvals are required for anything that changes state, and cannot be
  self-approved.
- Backups are manual and local. There is no cloud backup.
- No email, SMS or push notification of any kind.
- No uptime guarantee. Restarts are expected.
- macOS on Apple Silicon only.

## Escalation

- **SEV1** — contact the owner of this installation directly, immediately.
  Do not wait for a working day.
- **SEV2 and SEV3** — use the reporting format above and send it through the
  agreed channel.

There is no on-call rota and no 24/7 support during private alpha. If it is
urgent and it is a SEV1, contact the owner directly and say "SEV1".

---

Thank you. The bugs you find now are the ones nobody else has to.
