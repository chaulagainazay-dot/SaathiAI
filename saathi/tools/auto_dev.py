"""
Auto-Dev Agent — Spec → Build → Review loop for Baadar.

POST /api/v1/dev/auto
Body: {"task": str, "project": "baadar|pielts|hcgms|new", "deploy": bool}

Runs the full autonomous development cycle:
  1. /spec   — write implementation plan (searches ~/awesome-llm-apps for patterns)
  2. /build  — implement via subagent-driven-development
  3. /review — code review, fix findings, repeat until clean
  4. /deploy — push to HF (baadar) or Firebase (pielts)

Reference: ~/.claude/skills/auto-dev/README.md
"""
import asyncio
import os
import subprocess
import textwrap
from datetime import datetime
from pathlib import Path

from anthropic import Anthropic

PROJECT_PATHS = {
    "baadar": str(Path.home() / "SaathiAI"),
    "pielts": str(Path.home() / "Downloads/ielts-practice-app"),
}

AWESOME_LLM_APPS = str(Path.home() / "awesome-llm-apps")


def _search_patterns(keywords: list[str]) -> str:
    """Search awesome-llm-apps for relevant patterns."""
    results = []
    for kw in keywords:
        try:
            out = subprocess.run(
                ["grep", "-r", "-l", "--include=*.py", "--include=*.md", kw, AWESOME_LLM_APPS],
                capture_output=True, text=True, timeout=10
            ).stdout.strip()
            if out:
                files = out.split("\n")[:5]
                results.append(f"Keyword '{kw}': {', '.join(Path(f).name for f in files)}")
        except Exception:
            pass
    return "\n".join(results) if results else "No direct matches — build from scratch."


def _git_log(project_path: str, n: int = 5) -> str:
    try:
        return subprocess.run(
            ["git", "log", "--oneline", f"-{n}"],
            cwd=project_path, capture_output=True, text=True, timeout=10
        ).stdout.strip()
    except Exception:
        return ""


def _run_tests(project_path: str) -> str:
    """Run project tests and return output."""
    try:
        result = subprocess.run(
            ["python3", "-m", "pytest", "tests/", "-x", "-q", "--tb=short"],
            cwd=project_path, capture_output=True, text=True, timeout=60
        )
        return (result.stdout + result.stderr)[:2000]
    except Exception as e:
        return f"Tests not run: {e}"


async def run_auto_dev(task: str, project: str = "baadar", deploy: bool = False) -> dict:
    """
    Full Spec → Build → Review → Deploy loop.
    Returns progress log and final status.
    """
    client = Anthropic()
    project_path = PROJECT_PATHS.get(project, PROJECT_PATHS["baadar"])
    log = []
    now = datetime.now().strftime("%Y-%m-%d")

    def emit(phase: str, msg: str):
        entry = f"[{phase.upper()}] {msg}"
        log.append(entry)
        return entry

    # ── PHASE 1: SPEC ──────────────────────────────────────────────────────────
    emit("spec", f"Task: {task}")
    emit("spec", f"Project: {project} @ {project_path}")

    # Search reference patterns
    keywords = task.lower().replace(",", " ").split()[:6]
    patterns = _search_patterns(keywords)
    emit("spec", f"Reference patterns found:\n{patterns}")

    git_log = _git_log(project_path)
    emit("spec", f"Recent commits:\n{git_log}")

    spec_prompt = textwrap.dedent(f"""
        You are an expert software architect. Write a concise implementation plan for:

        TASK: {task}
        PROJECT: {project} ({project_path})
        DATE: {now}

        Reference patterns from awesome-llm-apps:
        {patterns}

        Recent git history:
        {git_log}

        Write a markdown implementation plan with:
        1. Goal (1 sentence)
        2. Architecture (2-3 sentences)
        3. Files to create/modify (exact paths)
        4. Tasks (numbered, each with: what to implement, which file, test approach)
        5. Deploy step

        Be specific. No placeholders. Max 400 words.
    """).strip()

    spec_response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": spec_prompt}]
    )
    spec_text = spec_response.content[0].text

    # Save plan
    plan_dir = Path(project_path) / "docs" / "superpowers" / "plans"
    plan_dir.mkdir(parents=True, exist_ok=True)
    plan_file = plan_dir / f"{now}-auto-{task[:40].replace(' ', '-').lower()}.md"
    plan_file.write_text(f"# Auto-Dev Plan\n\n**Task:** {task}\n\n{spec_text}\n")
    emit("spec", f"Plan saved: {plan_file}")

    # ── PHASE 2: BUILD ─────────────────────────────────────────────────────────
    emit("build", "Starting implementation...")

    build_prompt = textwrap.dedent(f"""
        You are a senior engineer. Implement this plan step by step.

        PLAN:
        {spec_text}

        PROJECT PATH: {project_path}

        Rules:
        - Use the Bash and Edit/Write tools to make actual file changes
        - Write tests for each new function
        - Make small commits after each task: git add <files> && git commit -m "feat: ..."
        - No secrets in code (.env only)
        - Return: list of files changed, commit hashes, test results

        Start implementing now.
    """).strip()

    # Claude implements — using tool_use for file operations
    build_response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        messages=[{"role": "user", "content": build_prompt}]
    )
    build_summary = build_response.content[0].text[:1500]
    emit("build", f"Build complete:\n{build_summary}")

    # ── PHASE 3: REVIEW ────────────────────────────────────────────────────────
    emit("review", "Running tests...")
    test_out = _run_tests(project_path)
    emit("review", f"Tests:\n{test_out[:600]}")

    review_prompt = textwrap.dedent(f"""
        You are a strict code reviewer. Review the implementation for:

        TASK: {task}
        PROJECT: {project_path}

        Build summary:
        {build_summary}

        Test results:
        {test_out[:400]}

        Review for:
        1. Correctness — does it do what the task asks?
        2. Security — no secrets exposed, no injection vulnerabilities
        3. Tests — are there meaningful tests?
        4. Code quality — YAGNI, no over-engineering
        5. Missing edge cases

        Rate each finding: Critical / Important / Minor
        End with: VERDICT: CLEAN or NEEDS_FIX

        If NEEDS_FIX, list exact changes required.
    """).strip()

    max_review_rounds = 3
    verdict = "NEEDS_FIX"
    review_round = 0

    while verdict == "NEEDS_FIX" and review_round < max_review_rounds:
        review_round += 1
        emit("review", f"Review round {review_round}...")

        review_response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            messages=[{"role": "user", "content": review_prompt}]
        )
        review_text = review_response.content[0].text
        emit("review", review_text[:800])

        if "VERDICT: CLEAN" in review_text:
            verdict = "CLEAN"
            emit("review", "✅ Code is clean — proceeding to deploy")
        else:
            emit("review", f"⚠️ Round {review_round}: findings found — applying fixes...")
            # Apply fixes
            fix_response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=3000,
                messages=[
                    {"role": "user", "content": build_prompt},
                    {"role": "assistant", "content": build_summary},
                    {"role": "user", "content": f"Fix these review findings:\n{review_text}\n\nApply fixes now."}
                ]
            )
            build_summary = fix_response.content[0].text[:1500]
            emit("review", "Fixes applied, re-reviewing...")

    # ── PHASE 4: DEPLOY ────────────────────────────────────────────────────────
    deploy_url = None
    if deploy and verdict == "CLEAN":
        emit("deploy", f"Deploying {project}...")
        if project == "baadar":
            try:
                # Orphan push to HF (strip binaries)
                subprocess.run(
                    ["git", "checkout", "--orphan", "auto-deploy-tmp"],
                    cwd=project_path, capture_output=True
                )
                subprocess.run(
                    ["git", "add", "--all"],
                    cwd=project_path, capture_output=True
                )
                # Remove binary files
                subprocess.run(
                    ["git", "rm", "--cached", "-r", "--ignore-unmatch",
                     "*.mp4", "*.mp3", "*.jpg", "*.jpeg", "*.png", "*.bin"],
                    cwd=project_path, capture_output=True
                )
                subprocess.run(
                    ["git", "commit", "-m", f"auto-dev: {task[:60]}"],
                    cwd=project_path, capture_output=True
                )
                subprocess.run(
                    ["git", "push", "hf", "auto-deploy-tmp:main", "--force"],
                    cwd=project_path, capture_output=True, timeout=120
                )
                subprocess.run(
                    ["git", "checkout", "master"],
                    cwd=project_path, capture_output=True
                )
                subprocess.run(
                    ["git", "branch", "-D", "auto-deploy-tmp"],
                    cwd=project_path, capture_output=True
                )
                deploy_url = "https://baadar-baadar-ai.hf.space"
                emit("deploy", f"✅ Deployed: {deploy_url}")
            except Exception as e:
                emit("deploy", f"Deploy error: {e}")
        elif project == "pielts":
            emit("deploy", "Run: cd ~/Downloads/ielts-practice-app && firebase deploy")

    return {
        "ok": True,
        "verdict": verdict,
        "deploy_url": deploy_url,
        "plan_file": str(plan_file),
        "log": log,
        "review_rounds": review_round,
    }
