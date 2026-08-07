# BRANCH_ANCESTRY_GRAPH

**Method:** `git merge-base --is-ancestor`, `git rev-list --left-right --count`, `git rev-list --count master..TIP`.  
Timestamps were not used as authority.

## Primary product linear chain (verified ancestor chain)

Every row below **contains** the prior tip (except where noted):

1. **master** — `67efcb3cd5ca52c2fb96052168253fdf286ff60a`
2. **m48** — `27b3bcf3ac58f92558c3b2c466a33c09dc823d14`
3. **m49.1** — `f41e756c169b3899cb96a6b922d990472df13433`
4. **m49.2** — `d8492a8993de6ea4e83c59d9aea37440e1676ee3`
5. **m49.3** — `0eb1592caa207ca61b250ec50a8fc9c6a3d1ba3c`
6. **m49.4** — `e024c0c0447def2322f7761203465b90d530d311`
7. **m50** — `154a247b26f466a8eb3019265ac50a2568745a14`
8. **m51** — `e8dd4a9b61eac6445ab3084ea8aa01c395f2cd7c`
9. **m52** — `7edb6094de38a6141800b28e95f65c2f697049c2`
10. **m53** — `6626dea9936e945d2172e39114f9ec5b34d21012`
11. **m61 (via M54–M61 side then absorbed)** — `2cd61738522ff68968d24e4db56981b42fb8b965`
12. **m304–m311** — `ed3dea7d6030e083473964784650b52b7ba08d5e`
13. **m312–m319** — `6639ca730ece11bce160a55a237fcaff8df3058c`
14. **m320–m327** — `5b505f1a119989ec78856f969cb9fe3184bc784f`
15. **m328–m335** — `6cdf72661834242eb4901f7eaf44a4425957db37`
16. **m336–m343** — `d2961e02f8b0967a7d1dc419a71bc9acc8ec5a47`
17. **ui-recovery** — `1647e192dfa5aa86113d386b86e96dca428e423f`
18. **full-e2e (local)** — `6b55013d52458628a19a065c49365a6ff0d3a9da`
19. **private-alpha excellence** — `53b9b20736d5acf4a7ca3a9bd25b68d01e666a5d`
20. **m344–m359 local tip** — `f5bc7cb428d43ed089afae7bb7fc1443f515ba6b`
21. **m369–m376** — `949afa68a4135aa94dbdaaf9aecfd618e0948c09`
22. **m377–m385** — `e9581f43848cf90283c7c4e1c0dbfbad65a4a531`
23. **fm-c1** — `f79726d5746ecd485210dee6af12a3ed33a9f01e`
24. **fm-c2** — `97dc6bfab840834f3430df347f526835d94f34cd`
25. **fm-i1…i6** — `8540e686f4a56d54b9dca8ec3d36004468fd0392`
26. **fm-i6.2 memory (RECOMMENDED)** — `e1738d7deec5f44600fbf0d99e2b8f74a4bc83d0`


### Important notes on the linear chain

1. **M54–M61** (private-alpha readiness through workflow persistence / spatial UI) are ancestors of `m304` and therefore of all later product tips, even though they appear as named milestone branches between m53 and the TG series.
2. **Trading Guardian M166–M303** are ancestors of `m304` (verified: foundation and risk tips are ancestors of m304).
3. **UI foundation (PR #2)** is already on `master`; later UI recovery and private-alpha voice work continue the product chain.

## The critical post-M369 divergence

After `m369` (`949afa68a4135aa94dbdaaf9aecfd618e0948c09`), history **forks**:

```text
m369 @ 949afa6
├── LINEAR harness chain → m377 → fm-c1 → fm-c2 → fm-i1… → fm-i6.2-mem @ e1738d7
│     (AgentHarness + LocalModelHarness + memory gate)
│
└── MERGE tip origin/m344-m351 @ 48510a9
      ├── Merge PR #16 (m369 into m344-local base)  [already content-equivalent to linear m369]
      └── Merge PR #17 (m17 scheduled-graph concurrency fix)
```

| Tip | Contains harness FM-I? | Contains m17 concurrency fix? | Containment score (of 58 peers) |
| --- | --- | --- | --- |
| `fm-i6.2-mem` `e1738d7deec5` | YES | NO | **55** (highest) |
| `m344-remote` `48510a9570d4` | NO | YES | 45 |
| Merge-base of the two | m369 `949afa68a413` | — | — |

**Left-right count** `m344-remote...fm-i6.2-mem` = **8 / 19**  
- Only on m344-remote: 2 merge commits + 6 m17 commits  
- Only on fm-i6.2-mem: 19 harness/docs commits (m377 through FM-I6.2-LIVE)

## Side / experiment branches (not on main product tip)

| Branch | SHA | Relationship |
| --- | --- | --- |
| `evaluation/twenty-readonly-sandbox` | `2c98319…` | Diverges from `m312`; **not** contained in fm-i6.2 or m344-remote |
| `milestone/saathios-ui-ux` | `efd67f4…` | Ancestor work merged via PR #2; tip has post-merge docs only |
| Dirty WIP on original m312 worktree | uncommitted | Baadar / local intelligence / evaluation — **not** part of any published tip |

## PR base correctness (structural)

Draft PRs #3–#14 and #18–#22 form a **stacked chain** where each PR's base is the prior milestone tip. That is correct for stack review, but:

- **Nothing from m48 onward is on `master`.**
- PR **#21** is based on **`master`** while its head already contains ~326 commits of product history → GitHub reports **~430k additions / 2342 files** — an **artificially giant** diff, not a true feature surface area.
- PR **#14** base is `m320` while head is full-e2e recovery that already sits later in the linear chain (contains m328–m336+); the PR base is **stale relative to actual ancestry** (work already includes later milestones).

## ASCII overview

```text
master (PR#1+#2)
  └─ m48 → m49.1–4 → m50 → m51 → m52 → m53
       └─ m54…m61 (platform UI/ops) ─┐
       └─ TG m166…m303 ──────────────┼→ m304…m311 → m312…m319 → m320…m327
                                     │      → m328…m335 → m336…m343
                                     │      → ui-recovery → full-e2e → private-alpha
                                     │      → m344…m359 → m369…m376
                                     │            ├─→ m377…fm-i6.2-mem  ★ recommended baseline
                                     │            └─→ (merge #16+#17) m344-remote
                                     │
                                     └─ twenty (from m312)  [KEEP_SEPARATE_EXPERIMENT]
```
