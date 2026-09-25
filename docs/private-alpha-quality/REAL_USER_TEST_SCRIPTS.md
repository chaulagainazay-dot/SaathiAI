# SaathiOS Private Alpha — Real User Test Scripts

Give the tester the script. Do not coach, do not point, do not explain the interface.
Silence while someone is stuck **is the measurement**.

For every script the observer records: time to completion, points of confusion, wrong clicks,
questions asked, errors seen, and steps abandoned.

Ground rule: if the tester cannot do it, the product is wrong. Never write "user error".

---

## Script A — First-time user (15–20 min, all cohorts)

1. Open SaathiOS at http://127.0.0.1:3000
2. Without being told, describe what kind of system this is and whether it is live
3. Sign in
4. Identify which workspace you are in
5. Describe what the dashboard is telling you
6. Open a project
7. Create a mission
8. Request approval for it
9. Find the status of the mission you just created
10. Sign out

**Watch for:** Does step 2 land? Does the user understand this is private alpha and not connected
to anything real? At step 3, is the sign-in control obvious, or does "Bootstrap + login" read as
first-time setup? (See defect PA-D-004.)

---

## Script B — Operator mission flow (20–30 min, Cohort B)

1. Create a project named `Test Project <your alias>`
2. Create a mission inside it
3. Edit the mission
4. Validate the mission
5. Submit it for approval
6. Find where it says the approval is pending
7. After the owner approves, execute it
8. Create a second mission and cancel it mid-flight
9. Inspect the result of the first mission
10. Find the evidence trail for it

**Watch for:** Is "pending" visible without asking anyone? Does cancellation confirm before acting?
Does the evidence trail mean anything to a non-engineer?

---

## Script C — Owner approval flow (15–20 min, Cohort A)

1. Open the Approval Center
2. For one request, state exactly what is being asked for and what authority it grants
3. Approve a valid request
4. Reject an invalid request and give a reason
5. Try to approve something you submitted yourself; describe what happens
6. Revoke an approval, if the interface supports it
7. Find the audit trail for everything you just did

**Watch for:** Step 2 is the important one. If the owner cannot state the scope of what they are
approving, the approval interface has failed regardless of whether the button works.
Step 5 must be refused by the system, and the refusal must be understandable.

---

## Script D — Voice and assistant (15–20 min, Cohorts A and B)

1. Send a text prompt to the assistant
2. Read the reply — is it clear when it has finished?
3. Enable voice output
4. Play a response aloud
5. Press Stop mid-sentence
6. Start a response, then navigate to another page while it is speaking
7. Use the microphone
8. Deny the microphone permission when the browser asks, and describe what happens
9. Recover by going back to text input
10. Try English, then Nepali

**Known objective fact:** this machine has **180 browser voices across 49 languages and zero
Nepali voices**. Step 10 cannot produce native Nepali speech. What matters is whether the
fallback is *honest and understandable* — silence with no explanation is a defect.

**Watch for:** Does Stop stop immediately, or at the end of the sentence? Does the browser
microphone indicator go out when the app says recording stopped?

---

## Script E — Failure and recovery (15–20 min, Cohort A)

1. Leave the app idle for over an hour, then use it — describe what you see
2. Get back in
3. Trigger a mission failure using safe test data
4. Find the diagnostics for that failure
5. Find the alert
6. Retry or recover the mission
7. Restart the application
8. Confirm your work is still there

**Watch for:** Step 1 exercises the expired-session path repaired in `6b55013`. Expected: the dead
session clears itself and a sign-in form appears with "Your session expired. Sign in again to
continue." A raw error, a stuck spinner or a blank screen is a regression — report it as P1.

Step 8 matters most. If a restart loses work, that is P0 and the release stops.

---

## Observer recording sheet

| Field | Value |
|---|---|
| Tester alias | |
| Role | owner / operator / viewer |
| Script | A / B / C / D / E |
| Build SHA | |
| Date | ISO 8601 with +05:45 |
| Started / finished | |
| Steps completed | n of 10 |
| Steps abandoned | |
| Errors seen | |
| Points of confusion | verbatim quotes preferred |
| Questions asked | |
| Issues raised | feedback IDs |
| Tester's overall comment | their words, not a summary |

File the sheet under `docs/private-alpha-quality/sessions/<alias>-<script>-<date>.md` and open one
feedback entry per distinct issue.
