# LICENSE_REVIEW

| Artifact | License | Classification |
| --- | --- | --- |
| openai/whisper-small (base) | MIT | COMMERCIAL_COMPATIBLE |
| Dragneel/whisper-small-nepali weights | Apache-2.0 | COMMERCIAL_COMPATIBLE_WITH_OBLIGATIONS |
| sparshrestha/finetuned-whisper-small-nepali | (inherits Whisper; card sparse) | LICENSE_UNCLEAR → treat as research until clarified |
| devrahulbanjara/whisper-small-nepali | Apache-2.0 | COMMERCIAL_COMPATIBLE_WITH_OBLIGATIONS |
| OpenSLR 54 training data | **CC BY-SA 4.0** | ShareAlike + attribution; commercial use allowed with obligations |
| Common Voice | CC-0 | COMMERCIAL_COMPATIBLE |
| FLEURS | CC BY 4.0 | COMMERCIAL_COMPATIBLE_WITH_OBLIGATIONS |
| Qwen3-ASR-Nepali | **community-use-1.0** | RESEARCH_ONLY / not product-primary |
| faster-whisper / CTranslate2 | MIT | COMMERCIAL_COMPATIBLE |

## Product rule

- Fine-tunes on OpenSLR 54 require **attribution** and ShareAlike awareness for dataset; model Apache/MIT weights OK with obligations.
- Qwen3 community-use is **not** accepted as product dependency without counsel.
- No weights bundled into the SaathiAI git tree (local `~/.saathi/stt-models/` only).

