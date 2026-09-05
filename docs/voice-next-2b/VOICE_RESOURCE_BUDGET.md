# VOICE_RESOURCE_BUDGET

Policy (`resource-budget.js`):

- neverLowerLlmMemoryGate = true
- browser STT → LOCAL_STT_ALLOWED
- heavy local STT + active LLM → LOCAL_STT_BLOCKED_RESOURCE_PRESSURE
- prefer unload STT when LLM active

Concurrent budget: frontend + backend + Ollama + VAD + browser STT OK; heavy STT model load not admitted without free headroom.
