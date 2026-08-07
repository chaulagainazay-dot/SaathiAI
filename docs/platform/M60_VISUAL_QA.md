# M60 — Visual QA

17 screenshots in `m60_evidence/screenshots/`: onboarding, onboarding_safety,
mission_new, mission_scope, mission_created, mission_plan, approval_new, actions,
notifications, evidence, saved_views, search, templates, workflows, reduced_motion,
mobile_onboarding, mobile_mission_new.

Reviewed for hierarchy, form clarity, progress visibility (stepper), blocked-state
clarity (readiness BLOCKED_*), authority clarity (RoleBoundaryNotice), focus states,
error placement, mobile usability, contrast, glow restraint, safety-status
visibility, and consistency with M58/M59 Glass Frame.

Defects found + fixed: command-palette double-open de-conflict (M59, retained);
approval-preview cert capture race → robust wait; muted-text contrast (M59 tokens
retained). Note: a transient cold-start "session expired" banner can briefly appear
on first load of a deep route and self-heals on reconcile — non-blocking.
