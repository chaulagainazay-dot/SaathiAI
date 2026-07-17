# M24 Security and Privacy

* No raw prompts/outputs in audit, usage, or circuit rows.
* No API keys or authorization headers stored.
* Binary float money rejected.
* OpenAI-compatible base URL allowlisted (SSRF-safe); production requires host allowlist.
* Metadata hosts / link-local blocked.
* Operator overrides cannot enable cloud fallback, production certification, kill bypass, or Trading Guardian.
* Storage failure fails closed before execution; uncertain post-execution outcomes go to reconciliation.
* Secret scan: no credentials added by M24.
