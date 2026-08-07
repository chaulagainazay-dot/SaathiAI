**Production authorized: false.** Local-only private alpha.

# Private Alpha First-Run

## Acknowledgement

Private alpha is **local-only**. You must pass `--ack-local-only` before init
proceeds.

## What first-run does

1. Runs prepare checks
2. Optionally bootstraps a local owner identity (password-based, no cloud IdP)
3. Selects organization and workspace
4. Optionally enables HCG and IELTSAlert demo packages
5. Records backup destination and notification preferences
6. Leaves automations **disabled**
7. Prints production-disabled notice

## What first-run never does

- Request API credentials
- Activate paid AI providers
- Connect production Firebase
- Connect live payment rails
- Bind public network interfaces
- Enable Trading Guardian live mode
- Deploy or expose services
