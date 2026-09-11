# ACCESSIBILITY_REPORT — UI-NEXT-3.1

## Browser cert (Playwright + axe-core)

```text
axe critical = 0
axe serious = 0
keyboard navigation = pass
visible focus = pass (focus-visible outlines retained)
reduced motion = pass
contrast = pass (Design DNA graphite tokens)
zoom = usable (layout flex/grid)
```

## Reduced motion

When `prefers-reduced-motion: reduce`:

- Voice loops disabled (LISTENING / TRANSCRIBING / THINKING / SPEAKING)
- Mode-enter choreography disabled
- Risk flash disabled
- Labels, badges, icons, focus preserved
- Functionality remains understandable via static color + text

## Animation focus

Motion interactions use buttons; no focus loss observed after mode/voice/trade selection.
