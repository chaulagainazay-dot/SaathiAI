"""SaathiAI Infrastructure Layer — the architectural home for platform services.

    Model Router · Browser Service · Connector Registry · Voice Engine · Diagnostics

None of these are business capabilities; they are the substrate every department
sits on. Departments import ONLY this layer and never learn whether they are
talking to Claude, OpenRouter, Playwright, Camofox, Telegram, or GitHub.

Migration policy (agreed M5.1):
- Implementation currently remains in the existing top-level modules for
  backward compatibility (the live VM runs them; ~20 modules import them).
- This package re-exports those modules so both import paths resolve to the
  SAME objects — zero duplication, nothing moved, nothing broken.
- NEW code (this milestone onward) imports from `saathi.infrastructure.*`.
- A future release physically relocates the implementations here and the old
  paths become the shims. See README.md.
"""

__version__ = "0.4.1-infrastructure"
__layer__ = "infrastructure"
