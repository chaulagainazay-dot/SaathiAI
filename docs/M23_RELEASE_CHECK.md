# M23 — Release Check Extensions

## New / extended rules

| rule_id | Intent |
|---------|--------|
| chat_runtime_missing | Canonical runtime file required |
| chat_governed_default_false | GOVERNED_CHAT_DEFAULT must be True |
| chat_legacy_execution_enabled | LEGACY_CHAT_EXECUTION must be False |
| chat_direct_sdk_import | No OpenAI/Anthropic SDK in chat |
| chat_direct_provider_url | No provider URLs in chat |
| chat_credential_read | No API key env reads in chat |
| chat_direct_llm_generate | No llm.generate AST usage in chat/adapter |
| chat_raw_prompt_log / chat_raw_output_log | No raw content logging patterns |
| chat_caller_retry | No chat-level retry loops |
| chat_trading_tool | No trading capability in chat |
| chat_adapter_missing_runtime | Adapter must call runtime |
| chat_residual_exception_present | Manifest must not reintroduce chat exception |
| chat_residual_count_nonzero | chat_residual_exception_count must be 0 |

## Command

```bash
.venv/bin/python -m saathi.inference.release_check --json
```

Offline, no network. Findings include path, line, symbol, detail.
