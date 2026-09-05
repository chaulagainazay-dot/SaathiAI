# Agent Operations Console

**Milestone:** M353
**Module:** `saathi/agentdev/console.py`
**Commands:** `console show` · `console state` · `console render`

One place to see the whole development environment. Fifteen panels, assembled
from the mission and artifact stores, the role registry, live git and the host.

M344–M351 shipped with limitation 6: *no operator console, dashboard or Control
Center surface; the CLI is the only interface*. This closes that, without
opening anything the CLI keeps shut.

---

## 1. What it is

```
python -m saathi.agentdev console show                     # terminal summary
python -m saathi.agentdev console state                    # full JSON
python -m saathi.agentdev console render --output out.html # one HTML file
python -m saathi.agentdev --store <dir> console show       # another store
```

`render` with no `--output` prints the page to stdout. With `--output` it writes
exactly one file, at the path the operator names, after checking that path
against the protected-configuration surface — pointing it at `~/.claude/` is
refused.

The HTML is self-contained: no script tag, no external stylesheet, no font, no
image, no network reference of any kind. It opens from a `file://` path with no
server and works in light and dark themes.

## 2. The fifteen panels

| # | Panel | Source | What it answers |
|---|---|---|---|
| 1 | Operator notices | derived | What needs a human, ordered blocker → warning → info |
| 2 | Missions | mission store | What is in flight, and every mission when none is |
| 3 | Blocked missions | mission store | What is stuck, and precisely why |
| 4 | Mission lifecycle | `missions.py` | The state machine, its exit gates and where missions sit |
| 5 | Agent hierarchy | role registry | Who escalates to whom, who reviews whom, authority ceilings |
| 6 | Review queue | artifact store | What is waiting for a reviewer, oldest first |
| 7 | Approvals | mission gates | Every gate decision, with a self-approval flag |
| 8 | Disagreements | artifact store | Challenges raised, which went unanswered |
| 9 | Evidence | artifact store | Artifact counts by kind and status, plus lineage edges |
| 10 | Worktrees | live git + registry | Census, and the four disagreement classes it finds |
| 11 | Certification | `docs/evidence/*/` | Verdict token per milestone |
| 12 | Repository | live git | Branch, HEAD, cleanliness |
| 13 | Active branches | live git | Every branch, agent branches marked |
| 14 | Integration candidates | mission store | Missions the owner could weigh, and the risks they carry |
| 15 | Resource usage | host | RAM, CPU, disk, load, peak RSS, declared ceilings |

A sixteenth card reports the M352 terminology guard.

## 3. Read-only, and how that is established

| Claim | Classification | How it is checked |
|---|---|---|
| The module defines no approve, advance, create, remove, prune, merge, push, deploy or run verb | `technically_enforced` | A test asserts each name is absent from the module |
| The source calls no store write method and no file-write primitive | `technically_enforced` | A test greps the source for `.put(`, `.advance(`, `.record_gate(`, `.set_status(`, `.open_veto(`, `.set_terminal_verdict(`, `os.replace`, `write_text`, `write_bytes`, `open(`, `mkdir` |
| Collecting and rendering leaves every byte of the store unchanged | `technically_enforced` | A test fingerprints every file with SHA-256 before and after |
| Reading an absent store creates nothing | `technically_enforced` | A test asserts the directory still does not exist |
| Git is only ever read | `technically_enforced` | All git goes through `run_read_only_git`, the same allowlist the worktree manager uses; destructive verbs are refused before `subprocess` |
| Rendered HTML reaches no network | `technically_enforced` | A test asserts no `<script`, `src=`, `href=`, `@import`, `http://` or `https://` appears |
| Hostile content in a mission title cannot execute | `technically_enforced` | Everything is escaped through `html.escape`; a test plants a `<script>` title |

The one file the surface can produce is the rendered page, and only where the
operator points it.

## 4. No polling

A view is a snapshot with a timestamp. Refreshing means running the command
again. Live polling would need a daemon, and a daemon is a background process
this milestone has no reason to add on an 8 GB host.

## 5. What the console cannot tell you

- **Whether an agent behaved well.** It shows what was recorded. Panels 7 and 8 will show a self-approval or an unanswered challenge if one reached disk; they cannot show a well-formed record that was written for the wrong reason.
- **Anything about a provider.** No panel contacts a model. Panel 15 measures the host and this process, not a model daemon.
- **Live state.** Between two snapshots, anything may have changed.
- **Whether a certification is deserved.** Panel 11 parses a verdict token from a Markdown file. `certification` is `documentation_only` — see [terminology.md](terminology.md).

## 6. Evidence

- `docs/evidence/m352_m359/AGENT_OPERATIONS_CONSOLE.html` — rendered page over the simulated mission
- `docs/evidence/m352_m359/AGENT_OPERATIONS_CONSOLE.txt` — the same snapshot as text
- `docs/evidence/m352_m359/console-screenshots/` — four screenshots of the rendered page in a browser
