# BROWSER_EVIDENCE — UI-NEXT-3.1

```json
{
  "mission": "UI-NEXT-3.1",
  "base": "http://127.0.0.1:3134",
  "motion_tech": {
    "primary": "CSS_SUFFICIENT",
    "gsap": "GSAP_RUNTIME_DEFERRED",
    "lottie": "LOTTIE_RUNTIME_DEFERRED",
    "three": "THREE_JS_DEFERRED"
  },
  "screenshots": [
    "01-command-idle.png",
    "02-voice-listening.png",
    "03-voice-transcribing.png",
    "04-voice-thinking.png",
    "05-voice-speaking.png",
    "06-voice-interrupting.png",
    "07-risk-warning.png",
    "08-risk-breached.png",
    "09-reconciliation-required.png",
    "10-proposal-ready.png",
    "11-proposal-blocked.png",
    "12-current-vs-proposed.png",
    "13-performance.png",
    "14-agent-active.png",
    "15-mission-progress.png",
    "16-evidence-focus.png",
    "17-mobile-command.png",
    "18-mobile-voice.png",
    "19-reduced-motion.png"
  ],
  "axe": [
    {
      "label": "command-motion-desktop",
      "critical": 0,
      "serious": 0,
      "violations": []
    },
    {
      "label": "command-motion-mobile",
      "critical": 0,
      "serious": 0,
      "violations": []
    }
  ],
  "axe_critical": 0,
  "axe_serious": 0,
  "findings": [
    {
      "id": "motion_attr",
      "ok": true
    },
    {
      "id": "keyboard_focus_after_motion",
      "ok": true
    },
    {
      "id": "reduced_motion",
      "ok": true
    }
  ],
  "verdict": "BROWSER_CERT_PASS"
}
```
