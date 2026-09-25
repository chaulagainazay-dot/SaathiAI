# CAPABILITY_UPDATE

When VAD adapter healthy:

```text
vadAvailable = true
acousticBargeInAvailable = true  (when microphone available)
manualInterruptAvailable = true
wakeWordAvailable = false
streamingSttAvailable = false
streamingTtsAvailable = false
fullDuplexAvailable = false
```

If VAD fails: vad/acousticBargeIn → false; manual interrupt retained.
