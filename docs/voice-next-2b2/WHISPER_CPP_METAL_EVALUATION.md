# WHISPER_CPP_METAL_EVALUATION

## Decision

**Not installed** for this milestone after CT2 specialized models failed the locked gate.

Rationale:

1. Same Whisper Small weights would not magically pass NE intent 0.15 → 0.60 solely via Metal.
2. Integration cost (ggml export of fine-tunes) non-trivial; no prebuilt ggml of Dragneel found.
3. Mission: do not introduce whisper.cpp merely for variety if CTranslate2 already answers the accuracy question.

## Classification

`whisper.cpp` remains **ADAPT** for future Metal EN path if a **gate-passing** NE checkpoint appears in ggml form.

