# Limitations

- Python dependencies largely range-pinned, not fully hash-pinned
- SBOM hashes are integrity evidence, not cryptographic signatures
- Clean-clone full npm install + production build + browser cert verified primarily in main worktree; clone stage is structural + import/source-audit with documented limitations
- Single-host SQLite storage
- Owner human sign-off not claimed
- Authorization framework is planning-only; real connectivity remains false
- Full npm install + production build + browser cert run in primary tree evidence; clone ran focused pytest