"""Pydantic-схемы: то, что уходит наружу и приходит внутрь."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import EventType, PitchLength, Status, Track, WorkFormat


class CompanyBase(BaseModel):
    name: str = Field(max_length=200)
    industry: str | None = None
    site: str | None = None
    notes: str | None = None


class CompanyCreate(CompanyBase):
    pass


class CompanyRead(CompanyBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


class EventBase(BaseModel):
    type: EventType = EventType.note
    title: str = Field(max_length=300)
    details: str | None = None
    happened_at: datetime | None = None
    calendar_event_id: str | None = None


class EventCreate(EventBase):
    pass


class EventRead(EventBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    vacancy_id: int
    happened_at: datetime


class VacancyBase(BaseModel):
    title: str = Field(max_length=300)
    source_url: str | None = None
    status: Status = Status.researched
    priority: int = Field(default=3, ge=1, le=5)
    match_note: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_note: str | None = None
    work_format: WorkFormat = WorkFormat.unknown
    location: str | None = None
    resume_used: str | None = None
    research_file: str | None = None
    applied_at: date | None = None
    next_action: str | None = None
    next_action_at: date | None = None
    track: Track | None = None
    feedback: str | None = None


class VacancyCreate(VacancyBase):
    company_name: str = Field(max_length=200)


class VacancyUpdate(BaseModel):
    title: str | None = None
    status: Status | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
    match_note: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_note: str | None = None
    work_format: WorkFormat | None = None
    location: str | None = None
    resume_used: str | None = None
    research_file: str | None = None
    applied_at: date | None = None
    next_action: str | None = None
    next_action_at: date | None = None
    track: Track | None = None
    feedback: str | None = None


class VacancyRead(VacancyBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company: CompanyRead
    created_at: datetime
    updated_at: datetime


class VacancyDetail(VacancyRead):
    events: list[EventRead] = []


class AddonRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    label: str
    text: str
    fits_track: bool = False   # усилена ли эта добавка под трек вакансии


class PitchBlockRead(BaseModel):
    """Кирпич в собранном виде: опорная фраза плюс отобранные добавки."""

    key: str
    title: str
    period: str | None = None
    core_line: str
    hint: str | None = None
    addons: list[AddonRead] = []


class FocusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    track: Track
    title: str
    emphasize: str
    drop: str


class TipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: str
    title: str
    body: str | None = None


class Pitch(BaseModel):
    """Рассказ о себе, собранный под конкретную вакансию и длительность."""

    length: PitchLength
    length_label: str
    track: Track | None = None
    vacancy_id: int | None = None
    vacancy_title: str | None = None
    company: str | None = None
    blocks: list[PitchBlockRead] = []
    focus: FocusRead | None = None
    highlights: list[str] = []   # что подчеркнуть именно для этой вакансии
    hooks: list[TipRead] = []
    faq: list[TipRead] = []
    avoid: list[TipRead] = []


class Stats(BaseModel):
    """Сводка по воронке."""

    total: int
    by_status: dict[str, int]
    applied_count: int
    reply_rate: float          # доля откликов, на которые пришёл хоть какой-то ответ
    stale: list[VacancyRead]   # отправлено больше недели назад, ответа нет
    upcoming: list[VacancyRead]  # есть next_action_at в ближайшие дни
