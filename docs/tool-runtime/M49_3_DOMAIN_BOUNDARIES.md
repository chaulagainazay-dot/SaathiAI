# M49.3 Domain Boundaries

| domain | decision |
|---|---|
| browser inspect fixture | MIGRATE_SAFE_READ_ONLY_SLICE (fixture) |
| browser mutation (ab_*) | DEFER_AND_DISABLE |
| engineering project_run | PROHIBIT freeform shell |
| engineering list/read project | LEGACY_BOUNDED / migrated list_projects |
| voice subprocess | DEFER (no freeform shell path) |
| IELTS deploy | DEFER_AND_DISABLE |
| IELTS local tools | LEGACY_BOUNDED where local |
| deployment | DEFER_AND_DISABLE / PROHIBIT |
| financial advisory | SUPPORTED_APPROVAL_REQUIRED (paper/advisory) |
| financial execution | PROHIBIT |
