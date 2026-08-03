# Twenty draft-publication base decision

Repository: `chaulagainazay-dot/SaathiAI`

Selected draft-PR base: `milestone/m312-m319-connectivity-governance` at
`6639ca730ece11bce160a55a237fcaff8df3058c`.

This is not selected merely because it is historical. Ancestry was measured:

| Candidate | Relationship to Twenty head before M360 | Decision |
| --- | --- | --- |
| `master` | ancestor, but 219 commits behind the Twenty head | Too broad for a reviewable bounded PR. |
| `milestone/m312-m319-connectivity-governance` | exact fork point; 0 base-only / 3 Twenty-only commits | Selected nearest valid parent. |
| `milestone/m320-m327-provider-contracts` | not an ancestor; 11 base-only / 3 Twenty-only commits | Rejected: opening against it would present unrelated reverse differences unless history were merged/rebased. |

M320–M327 is architecturally relevant but not a safe Git base for the existing
published-history-preserving branch. This mission forbids merging unrelated
history and does not rewrite the three evidence commits. The draft PR will state
that later integration needs an explicit ancestry strategy after review.

Publication constraints: draft only, no force push, no tag, no merge, no ready-for-
review transition, and no acceptance claim. The remote branch must match local
HEAD after every publication commit.
