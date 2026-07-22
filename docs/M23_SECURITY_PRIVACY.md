# M23 — Security and Privacy

## Chat high-risk controls

| Rule | Enforcement |
|------|-------------|
| No raw user messages in routine logs | runtime `_emit` strips prompt/text/system/messages |
| No raw assistant output in telemetry | `safe_telemetry` / event filters |
| No full history in telemetry | context metadata only (counts, fingerprints) |
| No credential reads in chat package | release_check `chat_credential_read` |
| No provider SDKs in chat package | release_check `chat_direct_sdk_import` |
| No provider URLs in chat package | release_check `chat_direct_provider_url` |
| log_prompt / log_output false | InferenceRequest defaults + caller policy |
| Production raw-chat debug denied | release_check + runtime defaults |

## Identity

* Conversation IDs normalized; unknown IDs fail closed when required
* Local single-user bound actor `user:ajay` (no auth redesign)
* Cross-conversation history rows denied in `select_history`
* Provider responses cannot change session ownership

## Tool / trading isolation

* Inference approval ≠ tool approval
* Tools default off; gateway remains execution authority
* No exchange SDKs; Trading Guardian UNCHANGED / UNENGAGED

## Secret scan

Scope: `saathi/chat/**` and inference facades — must remain clean.
