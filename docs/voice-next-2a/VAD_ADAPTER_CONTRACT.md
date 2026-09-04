# VAD_ADAPTER_CONTRACT

```text
start() / stop()
processAudioFrame(frame, meta?)
onSpeechStart(cb) / onSpeechEnd(cb)
health()
configure(partial)
setBargeInMode?(bool)
```

Implementation: `createEnergyVad` (`energy-vad.js`).
