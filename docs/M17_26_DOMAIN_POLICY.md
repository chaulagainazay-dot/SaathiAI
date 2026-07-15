# M17.26 Domain Policy

## Service

`saathi.browser.domain_policy.DomainPolicyService`

Environments: `development`, `test`, `staging`, `production`
(aliases: dev/local → development; prod/live → production).

## Normalization

* Lowercase hostnames; strip trailing dots
* IDN → punycode (flagged)
* Mixed-script host detection (denied when configured)
* IPv4/IPv6 classification: loopback, private, link-local, multicast, reserved
* Alternative IP forms (decimal/hex/octal) decoded when detected
* Canonical origin construction (default ports omitted)

Domain matching uses **exact host** or **explicit subdomain-of allowlisted root**
(`host == root` or `host.endswith("." + root)`). Never substring matching.
`example.com.attacker.test` does **not** match `example.com`.

## Production defaults

| Rule | Value |
|------|-------|
| Default | Deny |
| Schemes | HTTPS only |
| Localhost | Denied |
| Private / link-local IPs | Denied |
| IP literals | Denied (unless narrow config) |
| file:// javascript: data: | Denied |
| Custom protocols | Denied |
| Wildcards | Rejected |
| Subdomains of allowlist roots | **Not** automatic |
| Env override to skip validation | **None** |

Allowlist sources:

1. Constructor / session `allowed_hosts`
2. `SAATHI_BROWSER_ALLOWED_DOMAINS` (comma-separated exact hosts)
3. Empty production allowlist → deny all when browser enabled (config check)

## Redirects and popups

`check_redirect` / `check_popup` revalidate the destination with the same policy.
Silent redirects to unapproved domains are denied.

## Temporary exceptions

Optional structured exceptions (id, env, domain, scheme, port, action classes,
actor/mission, reason, approver, expiry, max uses). Expired and over-use fail
closed. Cannot authorize `file`/`javascript`/`data`, financial, or withdrawal.

Prefer explicit configuration over exceptions.

## Configuration checks

`production_config_violations(...)` returns blocking issues for empty allowlists,
wildcards, raw browser, file/private/custom protocol, screenshot without
redaction, traces without policy, unrestricted desktop.
