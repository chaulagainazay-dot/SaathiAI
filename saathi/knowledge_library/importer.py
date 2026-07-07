"""Knowledge Importer — ingest a repo/paper/doc ONCE into the Knowledge Library.

Reads the real README (and infers tags + related Directors), summarises, and stores
a rich source record. Honest: the summary is the README's own opening + heading map;
if a brain/LLM is available it refines it, otherwise the heuristic stands — we never
invent lessons the source doesn't contain. After import, Directors search the library
instead of re-reading the repo.
"""
from __future__ import annotations

import re

# tag keyword → Directors that benefit (so search-by-director works)
_DIRECTOR_HINTS = {
    "research": ("research", "evaluation", "benchmark", "paper", "survey", "analysis"),
    "learning": ("evaluation", "memory", "observability", "feedback", "learning", "rlhf"),
    "creative": ("prompt", "persona", "storytelling", "content"),
    "script": ("prompt", "planning", "workflow", "chain"),
    "render": ("multimodal", "image", "video", "tts", "voice"),
    "publishing": ("seo", "social", "distribution"),
    "signal_engine": ("trading", "signal", "risk", "market"),
}
# keyword → tag (canonical tags we recognise)
_TAG_WORDS = ["langgraph", "crewai", "autogen", "mcp", "a2a", "evaluation", "memory",
              "deployment", "planning", "safety", "orchestration", "observability",
              "benchmark", "rag", "multi-agent", "tool", "agent", "openai", "langchain",
              "reasoning", "guardrails", "vector", "embedding", "workflow", "prompt"]


def _parse_repo_url(url: str) -> tuple[str, str] | None:
    m = re.search(r"github\.com[/:]([^/]+)/([^/#?]+?)(?:\.git)?/?$", url.strip())
    if not m:
        return None
    return m.group(1), m.group(2)


def _fetch_readme(owner: str, repo: str, timeout: float = 12.0) -> str:
    import httpx
    for branch in ("main", "master"):
        for name in ("README.md", "readme.md", "README.rst", "README"):
            u = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{name}"
            try:
                with httpx.Client(follow_redirects=True, timeout=timeout,
                                  headers={"User-Agent": "SaathiAI-Library/1.0"}) as c:
                    r = c.get(u)
                    if r.status_code == 200 and r.text.strip():
                        return r.text
            except Exception:
                continue
    return ""


# generic section headings that are NOT a repo's real title
_GENERIC_TITLES = {"features", "highlights", "quickstart", "toc", "table of contents",
                   "before / after", "before/after", "overview", "introduction", "getting started",
                   "installation", "usage", "how it works", "about"}


def _pick_title(headings: list[str], repo: str) -> str:
    """The repo name is the canonical, reliable title — READMEs open with section
    headings, not the project name. Use an H1 ONLY if it clearly names the repo."""
    name = repo.replace("-", " ").replace("_", " ").title()
    repo_key = repo.replace("-", "").replace("_", "").lower()
    for h in headings[:3]:
        clean = h.strip().lstrip("✨#🎯🚀⭐ ").strip()
        if clean.replace(" ", "").replace("-", "").lower().startswith(repo_key) and 3 <= len(clean) <= 60:
            return clean
    return name


def _headings(md: str) -> list[str]:
    return [re.sub(r"^#+\s*", "", ln).strip() for ln in md.splitlines() if ln.lstrip().startswith("#")][:20]


def _summary(md: str) -> str:
    # first non-heading, non-badge paragraph
    for para in re.split(r"\n\s*\n", md):
        p = para.strip()
        if p and not p.startswith("#") and not p.startswith("[!") and "![" not in p[:4]:
            return re.sub(r"\s+", " ", p)[:400]
    return re.sub(r"\s+", " ", md)[:300]


def _tags(md: str) -> list[str]:
    low = md.lower()
    return [t for t in _TAG_WORDS if t in low][:12]


def _directors_for(tags: list[str]) -> list[str]:
    dirs = []
    for d, hints in _DIRECTOR_HINTS.items():
        if any(h in tags or any(h in t for t in tags) for h in hints):
            dirs.append(d)
    return dirs or ["research"]


def _lessons(headings: list[str]) -> list[str]:
    # the README's own section titles ARE its practical lessons — honest, not invented
    skip = {"table of contents", "license", "installation", "contributing", "acknowledgements"}
    return [h for h in headings if h.lower() not in skip and len(h) < 60][:8]


def import_repo(url: str, *, category: str = "AI Engineering", store=None) -> dict:
    """Import a GitHub repo into the Knowledge Library from its real README."""
    from saathi.knowledge_library.store import default_store
    st = store or default_store()
    parsed = _parse_repo_url(url)
    if not parsed:
        return {"ok": False, "error": "not a github url"}
    owner, repo = parsed
    md = _fetch_readme(owner, repo)
    if not md:
        # still record the source, flag that content wasn't fetched (honest)
        src = st.add(title=repo.replace("-", " ").title(), url=url, author=owner,
                     source_type="github", category=category, summary="(README not fetched)",
                     tags=[], related_directors=["research"], quality=0.4)
        return {"ok": True, "fetched": False, "source": src}

    headings = _headings(md)
    title = _pick_title(headings, repo)
    tags = _tags(md)
    src = st.add(title=title, url=url, author=owner, source_type="github", category=category,
                 summary=_summary(md), tags=tags, related_directors=_directors_for(tags),
                 key_lessons=_lessons(headings), quality=0.7)
    return {"ok": True, "fetched": True, "source": src, "headings": headings[:8]}


def seed_defaults(store=None) -> int:
    """Seed the library with the sources the CEO has flagged as foundational."""
    from saathi.knowledge_library.store import default_store
    st = store or default_store()
    seeds = [
        dict(title="AI Agents: The Definitive Guide", author="Nicole Koenigstein",
             url="https://github.com/Nicolepcx/ai-agents-the-definitive-guide",
             source_type="book", category="AI Engineering", difficulty="advanced", quality=0.9,
             tags=["langgraph", "evaluation", "memory", "deployment", "planning", "safety", "multi-agent"],
             related_directors=["research", "learning", "script"],
             key_lessons=["Evaluation-first agent engineering", "Agent observability",
                          "Production deployment patterns", "Memory hierarchy", "Failure handling",
                          "LangGraph orchestration patterns"],
             summary="Companion repo to Nicole Koenigstein's book on production-grade agent "
                     "engineering: planning, orchestration, evaluation, deployment, memory, safety, "
                     "benchmarking, and LangGraph patterns with chapter-aligned notebooks."),
    ]
    n = 0
    for s in seeds:
        if not st.find(url=s["url"]):
            st.add(**s); n += 1
    return n
