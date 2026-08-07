# M49.3 Connector Dry-Run Gates

Mutation-capable connector tools are **DRY_RUN_ONLY**.

Dry-run output includes: validated action/arguments, authority, approval requirement, target connector, side-effect class, idempotency requirement, safe preview, `network_performed=false`, `mutation_performed=false`.

Dry-run never: sends email, creates calendar events, modifies repositories, clicks browser controls, deploys, or changes account settings.
