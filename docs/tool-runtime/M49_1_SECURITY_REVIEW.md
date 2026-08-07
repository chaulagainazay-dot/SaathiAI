# M49.1 Security Review

| Finding | Severity | Status |
|---|---|---|
| Tool impersonation via registration | mitigated | trusted registration only |
| Manifest spoofing by caller | mitigated | code-owned manifests |
| Authority downgrade | mitigated | manifest-only |
| Approval bypass | mitigated | server-side approval ref |
| Secret injection | mitigated | reject + redact |
| Direct adapter bypass | partial | deferred voice tools |
| Financial execution | mitigated | PROHIBITED |
| Unsafe retry | mitigated | uncertain mutation not retryable |
| Unknown outcome misclass | mitigated | explicit outcome classes |

Critical: 0
High: 0 (deferred domain tools accepted as limitation)
