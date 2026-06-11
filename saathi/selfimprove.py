"""Self-improvement engine — Saathi gets better on its own, from real usage.

Three mechanisms, all local and safe (no self-rewriting of code):

  1. Feedback log — every failure, correction, blocked action, or "that's wrong"
     is recorded with context.
  2. Nightly reflection — an LLM pass over recent feedback turns it into concrete
     "learnings" stored as long-term facts, which feed every future answer.
  3. Auto-tuning — settings that we used to fix by hand (speaker-verification
     threshold) are recalibrated automatically from observed data.

Run a cycle manually:  python -m saathi.selfimprove
"""
import json
import sqlite3
import time
from pathlib import Path

from . import config

TUNING_PATH = config.ROOT / "data" / "tuning.json"

_db = sqlite3.connect(config.DB_PATH, check_same_thread=False)
_db.executescript("""
    CREATE TABLE IF NOT EXISTS feedback(
        id INTEGER PRIMARY KEY, kind TEXT, detail TEXT, ts REAL);
    CREATE TABLE IF NOT EXISTS verifications(
        id INTEGER PRIMARY KEY, sim REAL, verified INTEGER, ts REAL);
    CREATE TABLE IF NOT EXISTS improvements(
        id INTEGER PRIMARY KEY, summary TEXT, ts REAL);
""")


# ---------- 1. feedback capture ----------

def record_feedback(kind: str, detail: str = "") -> dict:
    """kind: 'wrong' | 'blocked' | 'error' | 'praise' | 'missed_wake' | ..."""
    _db.execute("INSERT INTO feedback(kind, detail, ts) VALUES(?,?,?)",
                (kind, detail, time.time()))
    _db.commit()
    return {"recorded": kind}


def record_verification(sim: float, verified: bool):
    _db.execute("INSERT INTO verifications(sim, verified, ts) VALUES(?,?,?)",
                (float(sim), 1 if verified else 0, time.time()))
    _db.commit()


# ---------- 2. nightly reflection ----------

def reflect() -> dict:
    """Summarize recent failures into durable learnings stored as facts."""
    since = time.time() - 7 * 86400
    rows = _db.execute(
        "SELECT kind, detail FROM feedback WHERE ts > ? ORDER BY ts DESC LIMIT 60",
        (since,)).fetchall()
    if len(rows) < 3:
        return {"skipped": "not enough feedback yet", "count": len(rows)}

    bundle = "\n".join(f"- [{k}] {d}" for k, d in rows)
    from .agent import SaathiAgent
    from .memory import Memory
    agent = SaathiAgent()
    system = ("You improve a voice assistant named Saathi for Ajay. Below is recent "
              "feedback about what went wrong. Output 1-3 SHORT, concrete learnings "
              "(one line each, imperative) that would prevent these problems next "
              "time. No preamble, just the lines.")
    learnings = agent.complete(system, bundle, max_tokens=250)

    mem = Memory(config.DB_PATH)
    saved = []
    for line in learnings.splitlines():
        line = line.strip("-• \t")
        if len(line) > 8:
            mem.save_fact(f"[self-learned] {line}", category="self_improvement")
            saved.append(line)
    summary = f"Reflected on {len(rows)} feedback items, saved {len(saved)} learnings."
    _db.execute("INSERT INTO improvements(summary, ts) VALUES(?,?)",
                (summary, time.time()))
    _db.commit()
    return {"learnings": saved, "summary": summary}


# ---------- 3. auto-tuning ----------

def autotune_threshold() -> dict:
    """Recalibrate the speaker-verification threshold from observed scores.

    Finds the natural gap between the 'noise/stranger' cluster (low scores) and
    the 'Ajay' cluster (high scores) and sets the threshold in that gap.
    """
    sims = sorted(s for (s,) in _db.execute(
        "SELECT sim FROM verifications WHERE ts > ? AND sim > 0.2",
        (time.time() - 14 * 86400,)).fetchall())
    if len(sims) < 20:
        return {"skipped": "need more voice samples", "have": len(sims)}

    # largest gap between consecutive scores within the decision zone
    best_gap, best_mid = 0.0, None
    for a, b in zip(sims, sims[1:]):
        if 0.5 <= a <= 0.85 and (b - a) > best_gap:
            best_gap, best_mid = b - a, (a + b) / 2
    if best_mid is None:
        return {"skipped": "no clear gap found"}

    new_thr = round(min(max(best_mid, 0.62), 0.82), 2)
    tuning = _read_tuning()
    old = tuning.get("speaker_threshold", config.SPEAKER_THRESHOLD)
    tuning["speaker_threshold"] = new_thr
    tuning["tuned_at"] = time.time()
    TUNING_PATH.write_text(json.dumps(tuning, indent=2))
    return {"old_threshold": old, "new_threshold": new_thr,
            "from_samples": len(sims), "gap": round(best_gap, 3)}


def _read_tuning() -> dict:
    if TUNING_PATH.exists():
        try:
            return json.loads(TUNING_PATH.read_text())
        except Exception:
            return {}
    return {}


# ---------- status + full cycle ----------

def status() -> dict:
    fb = _db.execute("SELECT kind, COUNT(*) FROM feedback GROUP BY kind").fetchall()
    last = _db.execute(
        "SELECT summary, ts FROM improvements ORDER BY ts DESC LIMIT 1").fetchone()
    return {"feedback_counts": dict(fb),
            "tuning": _read_tuning(),
            "last_reflection": (last[0] if last else "none yet")}


def run_cycle() -> dict:
    return {"reflect": reflect(), "autotune": autotune_threshold(),
            "status": status()}


if __name__ == "__main__":
    print(json.dumps(run_cycle(), indent=2, ensure_ascii=False))
