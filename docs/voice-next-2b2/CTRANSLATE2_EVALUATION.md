# CTRANSLATE2_EVALUATION

## Path exercised

```text
HF Whisper Small Nepali
  → ct2-transformers-converter --quantization int8
  → faster-whisper WhisperModel(local_path)
  → same adapter family as V-NEXT-2B.1
```

## Outcomes

| Model | Conversion | Runtime |
| --- | --- | --- |
| Dragneel | OK (retry without mandatory tokenizer copy) | OK |
| sparshrestha | OK after replacing broken tokenizer files with openai/whisper-small tokenizer | OK |
| devrahul | OK conversion | FAIL at decode (`list index out of range`) |

## Parity

Conversion is setup-time only; tooling not added to product runtime.

Accuracy insufficient for gate regardless of CT2 path health for Dragneel/sparshrestha.

