"""Database models.

Core tables:
  User     - a person in the global directory (reused across campaigns).
  Campaign - one phishing drill.
  Target   - one User included in one Campaign (carries the unique tracking token
             and a snapshot of their details at send time).
  Event    - every tracked interaction (open / click / confirm / report), with the
             raw IP + user-agent + timestamp and the detection verdict.

Training tables:
  TrainingModule   - a micro-lesson.
  TrainingQuestion - a quiz question belonging to a module.
  QuizResult       - a completed quiz attempt, tied back to a person via token.

The Event row is where the "click accuracy" story lives: we never throw away the
raw signals, so a result can always be defended with evidence instead of "trust us".
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EventType(str, Enum):
    OPEN = "open"          # tracking pixel loaded
    CLICK = "click"        # tracked link followed
    CONFIRM = "confirm"    # landing page ran JS -> a real, interactive browser
    REPORT = "report"      # recipient reported the email as phishing (good!)


class Verdict(str, Enum):
    HUMAN = "human"        # confident a real person did this
    SCANNER = "scanner"    # confident an automated scanner/proxy did this
    UNKNOWN = "unknown"    # not enough signal yet (e.g. click before JS confirm)


class CampaignStatus(str, Enum):
    DRAFT = "draft"
    SENT = "sent"


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = ""
    email: str = Field(index=True, unique=True)
    department: str = ""
    # Ethics gate: only people marked as consenting / authorised may be phished.
    consented: bool = True
    created_at: datetime = Field(default_factory=utcnow)


class StaffGroup(SQLModel, table=True):
    """A bucket for organising staff, e.g. 'New staff' or 'Failed phishing - Nov'.
    A user can belong to many groups (see StaffGroupLink)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    description: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class StaffGroupLink(SQLModel, table=True):
    """Many-to-many link between User and StaffGroup."""
    user_id: int = Field(foreign_key="user.id", primary_key=True)
    group_id: int = Field(foreign_key="staffgroup.id", primary_key=True)


class Campaign(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    from_name: str = "IT Security"
    from_email: str = "it-security@example.com"
    subject: str = "Action required: verify your account"
    status: CampaignStatus = Field(default=CampaignStatus.DRAFT)
    created_at: datetime = Field(default_factory=utcnow)
    sent_at: Optional[datetime] = None


class Target(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    campaign_id: int = Field(foreign_key="campaign.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    # Snapshot of the person at the time they were added to this campaign.
    email: str
    name: str = ""
    token: str = Field(index=True, unique=True)
    consented: bool = True


class Event(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    target_id: int = Field(foreign_key="target.id", index=True)
    campaign_id: int = Field(foreign_key="campaign.id", index=True)
    type: EventType
    created_at: datetime = Field(default_factory=utcnow)

    # Raw evidence - never discarded.
    ip: str = ""
    user_agent: str = ""
    http_method: str = "GET"

    # Detection output.
    verdict: Verdict = Field(default=Verdict.UNKNOWN)
    reason: str = ""
    # Seconds between the campaign send and this event (helps spot sub-second scans).
    seconds_since_send: Optional[float] = None


class TrainingModule(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(index=True, unique=True)
    title: str
    summary: str = ""
    body: str = ""          # the lesson text (newline-separated bullet points)
    order: int = 0


class TrainingQuestion(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    module_id: int = Field(foreign_key="trainingmodule.id", index=True)
    prompt: str
    choices_json: str = "[]"   # JSON-encoded list[str]
    correct_index: int = 0
    order: int = 0

    @property
    def choices(self) -> list[str]:
        try:
            return json.loads(self.choices_json)
        except (ValueError, TypeError):
            return []


class QuizResult(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    module_id: int = Field(foreign_key="trainingmodule.id", index=True)
    token: str = ""            # ties the attempt back to a Target/User if available
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    score: int = 0
    total: int = 0
    created_at: datetime = Field(default_factory=utcnow)
