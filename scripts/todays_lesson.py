#!/usr/bin/env python3
"""Print today's Mr. Yeti IELTS lesson topic from the 365-day curriculum.

Keeps pat_run.py frozen while wiring the curriculum in — feed it:

    .venv/bin/python scripts/pat_run.py "$(.venv/bin/python scripts/todays_lesson.py)"

Add --full for the day/phase/skill line. Anchor the program start with
SAATHI_CURRICULUM_START=YYYY-MM-DD, else it uses day-of-year.
"""
import os
import sys

sys.path.insert(0, os.path.expanduser("~/SaathiAI"))

from saathi.curriculum import today  # noqa: E402


def main():
    lesson = today()
    if "--full" in sys.argv:
        print(f"Day {lesson.day} · {lesson.phase} · {lesson.skill}: {lesson.topic}")
    else:
        print(lesson.topic)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
