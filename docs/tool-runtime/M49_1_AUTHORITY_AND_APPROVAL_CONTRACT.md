# M49.1 Authority and Approval

Authority from **manifest only**.

| Authority | Behavior |
|---|---|
| READ_ONLY | execute bounded |
| LOCAL_MUTATION | explicit approval |
| EXTERNAL_MUTATION | explicit approval |
| SECURITY_SENSITIVE | elevated approval |
| FINANCIAL_ADVISORY | approval + advisory |
| FINANCIAL_EXECUTION | PROHIBITED |
| UNKNOWN | reject / not registerable |

Approval reference checks: exists, active, not expired, not revoked, tool/capability/run/side-effect scope.
Frontend is not authorization.
