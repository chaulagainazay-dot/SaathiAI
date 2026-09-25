#!/usr/bin/env python3
"""M343 — emit the private-alpha launch checklist in machine and human form.

Reads the same evidence the readiness Control Center reads. Owner approval stays
OWNER_REVIEW_REQUIRED; there is no flag that changes it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from saathi.platform.private_alpha.launch_readiness import (  # noqa: E402
    KNOWN_LIMITATIONS,
    MAX_STATE,
    build_checklist,
    launch_readiness_report,
)

EVIDENCE = ROOT / "docs" / "private-alpha" / "m336_m343_evidence"
DOCS = ROOT / "docs" / "private-alpha"

STATE_MARK = {
    "PASS": "PASS",
    "PASS_WITH_LIMITATION": "PASS (with limitation)",
    "FAIL": "**FAIL**",
    "NOT_APPLICABLE": "n/a",
    "OWNER_REVIEW_REQUIRED": "**OWNER REVIEW REQUIRED**",
}


def main() -> int:
    report = launch_readiness_report()
    checklist = build_checklist()
    counts: dict[str, int] = {}
    for entry in checklist:
        counts[entry["state"]] = counts.get(entry["state"], 0) + 1

    machine = {
        "schema": "m343.private_alpha_launch_checklist.v1",
        "milestone": "M336-M343",
        "verdict": report["verdict"],
        "max_state": MAX_STATE,
        "owner_review_status": "OWNER_REVIEW_REQUIRED",
        "owner_review_may_be_automated": False,
        "release_is_automatic": False,
        "counts": counts,
        "total_items": len(checklist),
        "failed_items": [c for c in checklist if c["state"] == "FAIL"],
        "checklist": checklist,
        "known_limitations": KNOWN_LIMITATIONS,
    }
    out_json = EVIDENCE / "M343_LAUNCH_CHECKLIST.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(machine, indent=2, default=str) + "\n", encoding="utf-8")

    by_category: dict[str, list[dict]] = {}
    for entry in checklist:
        by_category.setdefault(entry["category"], []).append(entry)

    lines = [
        "# Private Alpha — Launch Checklist",
        "",
        f"**Verdict** `{report['verdict']}`  ",
        f"**Maximum state** `{MAX_STATE}`  ",
        "**Owner approval** `OWNER_REVIEW_REQUIRED` — automation may not mark this as passed.",
        "",
        "Generated from the same evidence the readiness Control Center reads. An item "
        "whose evidence file is missing reports FAIL rather than disappearing.",
        "",
        "| " + " | ".join(f"{state} {n}" for state, n in sorted(counts.items())) + " |",
        "|" + "---|" * max(1, len(counts)),
        "",
    ]
    for category in sorted(by_category):
        lines.append(f"## {category}")
        lines.append("")
        lines.append("| Item | State | Detail |")
        lines.append("| --- | --- | --- |")
        for entry in by_category[category]:
            detail = (entry["detail"] or "—").replace("|", "\\|")
            lines.append(
                f"| {entry['item']} | {STATE_MARK.get(entry['state'], entry['state'])} | {detail} |"
            )
        lines.append("")

    lines += [
        "## Known limitations",
        "",
        *[f"- {line}" for line in KNOWN_LIMITATIONS],
        "",
        "---",
        "",
        "`OWNER_REVIEW_REQUIRED` · `PRIVATE_ALPHA_RELEASE_NOT_AUTOMATIC` · "
        "`PUBLIC_PRODUCTION_NOT_AUTHORIZED`",
        "",
        "**Private-alpha readiness does not authorize public production deployment.**",
    ]
    out_md = DOCS / "PRIVATE_ALPHA_LAUNCH_CHECKLIST.md"
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({
        "verdict": report["verdict"],
        "counts": counts,
        "failed": len(machine["failed_items"]),
        "json": str(out_json),
        "markdown": str(out_md),
    }, indent=2))
    return 0 if not machine["failed_items"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
