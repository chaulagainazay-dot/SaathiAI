"""Director Library — run imported Directors through SaathiAI's own infra.

Each Director is a registered prompt (`director.<slug>`) executed via the Model
Router (Gemini 3.5 default). Departments/Studio call `run(slug, task, **ctx)`;
the Director's expertise comes from the agency prompt, but versioning, routing,
memory and evidence stay SaathiAI's. Brand-swappable per project.
"""
from __future__ import annotations

from saathi.infrastructure.model_router import ModelLabel


def list_directors() -> list[dict]:
    from saathi.production.agency_importer import catalog
    return catalog()


def run(slug: str, task: str, *, max_tokens: int = 900, **ctx) -> dict:
    """Run a Director on a task. Extra ctx is appended as structured context."""
    from saathi.ai_lab import default_registry
    reg = default_registry()
    name = slug if slug.startswith("director.") else f"director.{slug}"
    pv = reg.active(name)
    if not pv:
        return {"ok": False, "error": f"unknown director {slug!r} — run import_directors()"}

    full_task = task
    if ctx:
        import json
        full_task = task + "\n\nContext:\n" + json.dumps(ctx, default=str)[:1500]
    try:
        prompt = reg.render(name, task=full_task)
        from saathi.infrastructure.llm import generate
        res = generate(ModelLabel.STANDARD, prompt, "Be concise and actionable.", max_tokens=max_tokens)
        # feed the run back as an eval signal (non-blocking)
        try:
            reg.record_eval(name, pv.version, score=1.0 if res.text else 0.0, notes="director run")
        except Exception:
            pass
        return {"ok": True, "director": pv.name, "version": pv.version,
                "provider": res.provider, "output": res.text}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:120]}"}
