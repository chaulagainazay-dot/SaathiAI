# Security

## A protection bypass was found and fixed

`saathi/agentdev/config_protection.py::_home()` returned
`Path(os.path.expanduser("~"))` **unresolved**, while `classify_path()` compares
against a candidate that has been through `Path.resolve()`.

When `$HOME` is a symlink, the two disagree, `resolved.relative_to(home)` raises
`ValueError`, and the path falls through to `UNPROTECTED`.

Demonstrated:

```
HOME       : /var/folders/.../probe-home-onwy6uho
_home()    : /var/folders/.../probe-home-onwy6uho
resolved   : /private/var/folders/.../probe-home-onwy6uho/.claude/settings.json
protected  : False        ← should be True
```

**Impact.** An agent writing `~/.claude/settings.json`, `~/.claude/hooks.json`,
`~/.ssh/id_rsa`, or `~/.aws/credentials` would be allowed through whenever the
operator's home is symlinked. macOS `/var` → `/private/var` is the common case,
but any symlinked home directory does it. `assert_write_allowed()` and
`assert_change_allowed()` both route through `classify_path`, so the bypass
reached every caller.

This was **not** a test-only artifact. It was latent in production and was
exposed because the test session set `HOME` to a temp directory.

**Fix.** `_home()` now resolves, matching how candidates are resolved, with a
fallback to the unresolved path if resolution raises.

**Regression tests.** `tests/test_infra/test_state_isolation.py`:
`test_symlinked_home_still_protects_user_config`,
`test_home_resolution_is_symlink_stable`,
`test_protected_surfaces_remain_protected_under_redirected_home`.
The first asserts the temp dir really is symlinked and fails loudly on a
platform where the regression cannot be reproduced, rather than passing
vacuously.

## Tests no longer read or write the operator's real state

Before this milestone an unfiltered run touched ~30 real `~/.saathi` stores —
including `security.db` (users, sessions, API tokens, audit log),
`accounts.db`, and `.connector_key`. It also rewrote tracked files under
`docs/evidence/**`.

Both are now isolated, and `tests/test_infra/test_state_isolation.py` asserts it
on every run rather than relying on anyone remembering.

**Anyone who ran this suite before should assume their real `~/.saathi` stores
contain test-generated data.**

## No new attack surface

No network egress added. No credential added. No secret introduced. No broker,
no live endpoint. The CI workflow has no secrets and requires none.
