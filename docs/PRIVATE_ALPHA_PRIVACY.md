**Production authorized: false.** Local-only private alpha.

# Private Alpha Privacy

## Support bundle must not include

- API keys, tokens, passwords, cookies
- Full environment dumps
- Private HCG customer content
- Private IELTS submissions / raw essays
- Raw transcripts or audio
- Hidden prompts

## Config

- `support_bundle_privacy`: `strict` (default) or `standard`
- Redaction applied to logs included in bundles
- Secret-shaped keys rejected at config validation

## Data residency

Single-machine local storage under the repository `data/` tree and
`~/.saathi/` runtime logs/PIDs. No multi-tenant public cloud.
