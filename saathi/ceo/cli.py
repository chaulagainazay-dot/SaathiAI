"""M14 CEO OS CLI — `python -m saathi.ceo.cli <cmd>`.

  inspect / health        portfolio + system health (read-only)
  portfolio               portfolio summary (read-only)
  brief                   generate the Daily Brief (persists a brief record)
  goals / kpis / risks / opportunities / decisions / finance   (read-only lists)
  priorities              ranked items with score explanations (read-only)
  review-week             generate + persist a weekly review

Exit codes: 0 ok · 2 bad command. Read-only commands never mutate. Mission
creation / decision finalization / budget changes are NOT in the CLI — they
require the authenticated API path (authorization + approval).
"""
from __future__ import annotations

import json
import sys

from saathi.ceo.store import default_store
from saathi.ceo.service import CEOService

OWNER = "ajay"


def _emit(o) -> None:
    print(json.dumps(o, indent=1, default=str))


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print(__doc__)
        return 0
    cmd, *rest = argv
    st = default_store()
    svc = CEOService(st)

    if cmd in ("inspect", "health"):
        _emit(svc._system_health())
        return 0
    if cmd == "portfolio":
        _emit(svc.portfolio_summary(OWNER))
        return 0
    if cmd == "brief":
        _emit(svc.daily_brief(OWNER))
        return 0
    if cmd == "goals":
        _emit({"goals": st.list_goals(OWNER)})
        return 0
    if cmd == "kpis":
        from saathi.ceo.kpi import compute_kpi
        _emit({"kpis": [compute_kpi(st, k["id"]).to_dict() for k in st.list_kpis(OWNER)]})
        return 0
    if cmd == "risks":
        _emit({"risks": st.list_risks(OWNER)})
        return 0
    if cmd == "opportunities":
        _emit({"opportunities": st.list_opportunities(OWNER)})
        return 0
    if cmd == "decisions":
        _emit({"decisions": st.list_decisions(OWNER)})
        return 0
    if cmd == "finance":
        from saathi.ceo.finance import financial_summary
        _emit(financial_summary(st, OWNER))
        return 0
    if cmd == "priorities":
        from saathi.ceo import priority as PR
        ranked = [(f"risk:{r['id']}", PR.PriorityInput(risk_reduction=r["impact"]))
                  for r in st.list_risks(OWNER)[:10]]
        _emit({"priorities": PR.rank(ranked)})
        return 0
    if cmd == "review-week":
        _emit(svc.weekly_review(OWNER))
        return 0

    print(f"unknown command: {cmd}\n{__doc__}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
