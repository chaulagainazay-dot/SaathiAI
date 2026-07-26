# M59 — Runtime Attention Center (Workstream 4)

Routes: `/platform/attention` (list) · `/platform/attention/[attentionId]` (detail).

## What an attention item is

Attention items are runtime **executions** the backend flagged (they carry
`attention_reasons`), from `GET /api/v1/platform/runtime/attention`. Severity is
computed with the existing `attentionSeverity()` + `severityRank()` helpers, taking
the worst reason. Empty reasons → informational.

## List — four severity lanes

Critical · High · Medium · Informational (low folds into medium). Critical items
render as a top glass lane with a status pulse — **never** hidden behind hover or
animation. Filter by severity; total count shown. Empty state renders an explicit
"Runtime is clear" panel.

## Detail

An attention item IS an execution, so detail =
`GET /runtime/executions/{id}` + `.../timeline`, merged with the
`attention_reasons` from the list. Sections: human-readable explanation, affected
object (execution state, error code, recovery count, timestamps), related objects
(mission / agent / approval, each navigable), lifecycle timeline, governed action.

## Actions — no invented remediation

There is **no acknowledge / resolve API**, so those controls are not offered. The
only mutating action is a single **governed cancel**, shown only when
`canCancelExecution()` reports the execution state eligible, routed through
`POST /runtime/executions/{id}/cancel`. Recovery (resume / reconcile) remains on the
Operations workspace. Every action reconciles from the server afterwards.
