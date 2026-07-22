# M15 — Universal Tool and Connector Platform (Spec)

**Constitution:** v1.0 (`.specify/memory/constitution.md`)

## Problem
SaathiOS reaches external systems (Gmail, Calendar, GitHub, Telegram, browser,
databases, deployment, content publishing, MCP servers) through scattered,
per-feature integration code. There is no single governed layer enforcing risk,
approval, idempotency, credentials, health, and evidence.

## Objective A — Universal Connector Platform
One canonical integration layer with: connector/tool/result models, capability
catalog, registry, credential references (metadata only), lifecycle state
machine, risk model (0–4), approval binding to the exact action, idempotency,
rate limits, failure classification, health, webhooks (signature+replay), sync
(checkpoints), MCP (untrusted), deterministic adapters, evidence/provenance —
all executing through the ExecutionGateway. No connector bypasses the gateway;
no agent bypasses connector policy.

## Objective B — Spec-Driven Delivery Governance
A native, offline Spec Kit wrapper (constitution → spec → plan → tasks →
traceability → convergence) enforcing the Delivery Constitution, with a
convergence gate that fails on any unmapped or untested requirement.

## Non-goals
Live cloud OAuth flows in this environment (credentials absent → those
connectors are contract-ready / environment-blocked, never faked). Vendoring
external repos (garrytan/gstack is a SaaS starter, not Spec Kit).

## Requirements
See `traceability.json` (M15-CONN-001..015, M15-SPEC-001..004).
