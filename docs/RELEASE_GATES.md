# Release Gates (M13.5)

`python -m saathi.ops release-check` — machine-readable go/no-go.

## Hard gates (a staging release fails on any)
tests fail · critical manifest fails · secret scan (strong rules) fails · db integrity fails · schema mismatch · frontend/backend version mismatch · disk below block threshold · required provider unavailable · backup cannot be created · restore verification fails · authenticated browser smoke fails · approval enforcement fails · security P0 · git dirty · tracked private data.

## Exit codes
`0` ready · `1` warning-only · `2` test failure · `3` security failure · `4` config failure · `5` database failure · `6` backup/restore failure · `7` browser verification failure · `8` provider failure · `9` storage failure · `10` version mismatch · `11` dirty repository · `12` internal error.

## What `release-check` covers automatically
storage threshold, config validation (secret-redacted), db integrity (all 5), **real backup + isolated restore + verify**, strong-credential secret scan (test/doc excluded). Test-suite, critical-manifest, and browser gates run separately (they are slow / need a browser) and are part of the full validation ladder.
