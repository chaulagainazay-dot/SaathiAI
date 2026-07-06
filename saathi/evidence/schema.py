"""The universal Evidence schema — the company's shared memory.

Every department (AI Studio, PIELTS, HCG, Cafeteria, Travel, Telegram) writes
the SAME shape. That is the whole point: the CEO queries ONE table for the truth
across every business, and the Learning departments find patterns across them.
Native events differ; adapters normalise them into this record. Keep this schema
stable — adapters absorb change, the schema does not.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field


@dataclass
class Evidence:
    department: str                    # ai_studio | pielts | hcg | cafeteria | travel | telegram
    project: str = ""                  # brand / channel (mr_yeti, pielts, ...)
    episode: str = ""                  # unit of work (episode / essay / trade / menu-day)
    run: str = ""                      # specific run id
    director: str = ""                 # which Director / component produced it
    workflow: str = ""                 # workflow version
    prompt_version: str = ""           # AI Lab prompt version used
    provider: str = ""                 # engine family (gemini, ffmpeg, kokoro, ...)
    model: str = ""                    # exact model / engine id
    cost: float = 0.0
    latency_ms: float = 0.0
    confidence: float = 0.0
    status: str = ""                   # ready | revision | published | win | loss | ...
    metrics: dict = field(default_factory=dict)     # CTR, retention, band, sales, win/loss …
    feedback: dict = field(default_factory=dict)     # human rating, comments
    artifacts: dict = field(default_factory=dict)    # names → present/paths
    recommendation: str = ""           # what the Learning layer later attaches
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    timestamp: float = field(default_factory=time.time)

    def to_row(self) -> tuple:
        return (self.id, self.timestamp, self.department, self.project, self.episode, self.run,
                self.director, self.workflow, self.prompt_version, self.provider, self.model,
                float(self.cost), float(self.latency_ms), float(self.confidence), self.status,
                json.dumps(self.metrics), json.dumps(self.feedback), json.dumps(self.artifacts),
                self.recommendation)

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        return d


COLUMNS = ["id", "timestamp", "department", "project", "episode", "run", "director", "workflow",
           "prompt_version", "provider", "model", "cost", "latency_ms", "confidence", "status",
           "metrics", "feedback", "artifacts", "recommendation"]
_JSON_COLS = {"metrics", "feedback", "artifacts"}


def row_to_dict(row) -> dict:
    d = dict(zip(COLUMNS, row))
    for c in _JSON_COLS:
        try:
            d[c] = json.loads(d[c]) if d[c] else {}
        except Exception:
            d[c] = {}
    return d
