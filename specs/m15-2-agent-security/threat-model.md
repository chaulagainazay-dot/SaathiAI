# M15.2 Threat Model (STRIDE)

## Assets
System instructions, user/project data, M9 memory, credentials + connector
accounts, git repos, email/calendar, browser sessions, deployment targets,
generated media, approval tokens, agent permissions, audit evidence.

## Threat actors
Malicious user, compromised document/webpage/email, malicious MCP server,
compromised connector/provider output, poisoned memory, compromised delegated
agent, external attacker, accidental unsafe model behavior.

## Trust boundaries (untrusted → trusted)
user→Chat, document→retrieval, memory→prompt context, agent→agent,
agent→connector, connector→provider, MCP→connector platform, webhook→event bus,
browser page→agent, Voice transcript→approval, external response→memory write-back.
All content crossing these is DATA, never instructions.

## STRIDE mapping
| STRIDE | Threat | Control (verified by probe) |
|--------|--------|------------------------------|
| Spoofing | forged approval id / cross-user identity | approval binding + ownership check (APPROVAL-003, ISO-001/002) |
| Tampering | changed input after approval; MCP risk downgrade | input-hash binding; MCP clamp (APPROVAL-001, MCP-001) |
| Repudiation | action without record | execution + event records (evidence in every result) |
| Information disclosure | secret extraction | resolver scope check + redaction (SECRET-001/002, PI-002) |
| Denial of service | retry storms / event floods | no-retry on uncertain/non-idempotent; rate buckets (RETRY-001/002) |
| Elevation of privilege | agent self-approval; delegation widening | agent side effect gated; no self-approve (PRIV-001, GOAL-001) |

## Security properties enforced
confidentiality, integrity, authorization, least privilege, non-repudiation,
scope isolation, safe failure, approval integrity, secret protection, execution
containment.

## Environment limits (honest)
Live LLM/judge + HackAgent not available → adversarial-model generation is
ENVIRONMENT BLOCKED; deterministic probes are authoritative. Interactive browser
+ Voice runtime attack paths environment-blocked (no running authenticated
session). Cloud connector attack surfaces environment-blocked (no credentials).
