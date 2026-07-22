# M15.1 — Connector Platform Staging Completion (Spec)

**Constitution:** v1.0. Promotes M15 from DEVELOPMENT READY toward STAGING READY.

## Objective
Complete the staging-facing layer on top of the M15 core (do NOT rebuild it):
authenticated REST API, real connector UI, representative live wiring, credential
hardening, legacy migration, Chat/Agent/CEO/Voice integration, failure-path +
backup verification, observability.

## Architecture (no caller bypasses the platform)
User/Chat/Agent/CEO/Voice → Authenticated Connector API → Registry → Capability
Resolution → ExecutionEngine → ExecutionGateway → Risk/Approval → Credential
Reference Resolution → Adapter → External Service → Normalized Result → Evidence
→ Event Bus → Memory → UI/Chat/Agent/CEO.

## Non-goals / honest limits
No live cloud credentials in this environment → Gmail/Calendar/Contacts/Telegram/
publishing stay environment-blocked (implemented + contract-ready, never faked).
Browser: frontend build verified; interactive browser smoke is environment-blocked
unless a live authenticated session + running server is available.

## Requirements
See traceability.json (M15-1-API/AUTH/SEC/CRED/UI/LIVE/MIG/CHAT/AGENT/CEO/VOICE/
FAIL/BACKUP/OBS).
