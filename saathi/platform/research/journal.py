"""Auditable decision journal; retrospective analysis has no policy authority."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
class LessonStatus(str,Enum): OBSERVED='OBSERVED'; VALIDATING='VALIDATING'; PROMOTED='PROMOTED'; REJECTED='REJECTED'; EXPIRED='EXPIRED'
@dataclass(frozen=True)
class InvestmentDecisionRecord:
 decision_id:str; instrument_id:str; decision_time:datetime; thesis_id:str; status:str; expected_direction:str; intended_horizon:str; research_run_id:str|None=None; research_snapshot_id:str|None=None; challenge_session_id:str|None=None; assumptions:tuple[str,...]=(); invalidation_conditions:tuple[str,...]=()
@dataclass(frozen=True)
class DecisionOutcome:
 outcome_id:str; decision_id:str; observation_start:datetime; observation_end:datetime; instrument_return:Decimal|None; benchmark_return:Decimal|None
 @property
 def benchmark_status(self): return 'BENCHMARK_UNAVAILABLE' if self.benchmark_return is None else 'AVAILABLE'
@dataclass
class InvestmentLesson:
 lesson_id:str; origin_decision_ids:tuple[str,...]; statement:str; lesson_type:str; scope:str; instrument_scope:str|None; available_at:datetime; valid_until:datetime|None; status:LessonStatus=LessonStatus.OBSERVED; sample_size:int=0; version:int=1
 def __post_init__(self):
  if not self.origin_decision_ids: raise ValueError('lesson requires origin provenance')
def lessons_visible(lessons, at): return [l for l in lessons if l.status==LessonStatus.PROMOTED and l.available_at<=at and (l.valid_until is None or at<=l.valid_until)]
def promote(lesson,sample_size,minimum=3):
 if sample_size<minimum: return 'REJECTED'
 lesson.status=LessonStatus.VALIDATING; return 'REVIEW_REQUIRED'
class DecisionJournal:
 def __init__(self): self.decisions={}; self.outcomes={}
 def record(self,d):
  if d.decision_id in self.decisions:return 'DUPLICATE'
  self.decisions[d.decision_id]=d; return 'RECORDED'
 def add_outcome(self,o): self.outcomes.setdefault(o.outcome_id,o)
