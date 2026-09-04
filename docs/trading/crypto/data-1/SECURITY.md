# Security review

Only the fixed Binance public host is used; caller input cannot choose a URL. No redirects are followed by policy, no credentials are read or logged, payloads are bounded and treated as untrusted data, and no provider text is interpreted as instructions. No execution/account imports exist in the adapter.
