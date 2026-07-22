# M17.26 Evidence Classification and Redaction

## Pipeline

`saathi.browser.evidence_redaction.EvidenceRedactionPipeline`

For each governed interactive action (via `InteractiveBrowser.act`):

1. Classify page + action sensitivity  
2. Select redaction mode (highest risk wins)  
3. Resolve protected regions (deterministic)  
4. Capture screenshot **only if permitted**  
5. Mask **before** persistence (never store raw first)  
6. Persist hash + storage reference + retention expiry  
7. Emit redaction audit metadata  
8. Alerts never include screenshot bytes or secrets  

## Classification

```text
PUBLIC
INTERNAL
CONFIDENTIAL
SENSITIVE_PERSONAL
AUTHENTICATION_SECRET
FINANCIAL_SENSITIVE
MEDICAL_SENSITIVE
TRADING_SENSITIVE
PROHIBITED_CAPTURE
```

## Redaction modes

```text
ALLOW < MASK_FIELDS < MASK_REGIONS < BLUR_SENSITIVE < METADATA_ONLY < SUPPRESS_SCREENSHOT
```

Authentication, financial, medical, trading, and prohibited classes default to
**SUPPRESS_SCREENSHOT**.

## Deterministic sources (primary)

* Sensitive selectors (password, otp, card, cvv, api_key, …)
* Input types (`password`, …)
* ARIA labels
* Autocomplete attributes
* Page element metadata / bboxes
* Mission sensitivity tags
* User-defined protected regions
* Action class / trading classification

## OCR policy

* Optional secondary only when already available  
* Never required for milestone completion  
* Forbidden on authentication-secret captures  
* OCR failure must not expose sensitive screenshots (suppression remains)  
* OCR text treated as sensitive; not stored by default  

## DOM / trace / video

| Type | Default | Notes |
|------|---------|-------|
| DOM | Bounded, redacted nodes | No full source; secret values stripped |
| Trace | **Disabled** | Require retention + redaction policy if enabled |
| Video | **Disabled** | Screenshot redaction does **not** cover video |
| Cookies / storage_state | Never logged | `secrets_not_logged` |

## Retention

Per-class day defaults (PUBLIC 90 … AUTH 1 … PROHIBITED 0).  
`retention_expiry` recorded on every evidence record.

## Trading

Trading-classified pages use `TRADING_SENSITIVE` and suppress ordinary screenshots.
Trading credentials never stored in evidence.
