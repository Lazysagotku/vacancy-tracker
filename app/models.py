"""Доменные модели трекера откликов."""

from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Status(str, enum.Enum):
    """Где вакансия находится в воронке."""

    researched = "researched"      # разобрана, отклик не отправлен
    applied = "applied"            # отклик отправлен
    screening = "screening"        # анкета или скрининг рекрутёра
    interview = "interview"        # назначено или пройдено интервью
    offer = "offer"
    rejected = "rejected"          # отказ работодателя
    declined = "declined"          # отказался сам
    skipped = "skipped"            # решили не откликаться
    reserve = "reserve"            # держим на случай отказа по другой


class WorkFormat(str, enum.Enum):
    office = "office"
    hybrid = "hybrid"
    remote = "remote"
    unknown = "unknown"


class EventType(str, enum.Enum):
    note = "note"
    applied = "applied"
    questionnaire = "questionnaire"   # прислали анкету
    reply = "reply"                   # ответ рекрутёра
    call = "call"                     # созвон
    interview = "interview"
    test_task = "test_task"
    offer = "offer"
    rejection = "rejection"


class Track(str, enum.Enum):
    """Тип вакансии - от него зависят акценты в рассказе о себе."""

    dev = "dev"          # C#/.NET разработчик
    support = "support"  # поддержка, 2-3 линия
    ai = "ai"            # ИИ-инженер, автоматизация


class PitchLength(str, enum.Enum):
    """Сборки рассказа по времени."""

    short = "short"        # 40 секунд, HR просит коротко
    standard = "standard"  # 2 минуты, основной вариант
    full = "full"          # 4-5 минут, технарь просит подробно


# Сколько добавок брать на блок в каждой сборке
ADDONS_PER_LENGTH = {
    PitchLength.short: 0,
    PitchLength.standard: 2,
    PitchLength.full: 4,
}


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    industry: Mapped[str | None] = mapped_column(String(200))
    site: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    vacancies: Mapped[list["Vacancy"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    contacts: Mapped[list["Contact"]] = relationship(back_populates="company", cascade="all, delete-orphan")


class Vacancy(Base):
    __tablename__ = "vacancies"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    source_url: Mapped[str | None] = mapped_column(String(1000))

    status: Mapped[Status] = mapped_column(Enum(Status, name="vacancy_status"), default=Status.researched, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=3)  # 1 - высший, 5 - низший
    match_note: Mapped[str | None] = mapped_column(Text)       # чем подходим, где пробелы

    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    salary_note: Mapped[str | None] = mapped_column(String(300))
    work_format: Mapped[WorkFormat] = mapped_column(Enum(WorkFormat, name="work_format"), default=WorkFormat.unknown)
    location: Mapped[str | None] = mapped_column(String(300))

    resume_used: Mapped[str | None] = mapped_column(String(100))   # какое из трёх резюме приложили
    research_file: Mapped[str | None] = mapped_column(String(500)) # путь к разбору в career-notes
    applied_at: Mapped[date | None] = mapped_column(Date)
    next_action: Mapped[str | None] = mapped_column(String(300))
    next_action_at: Mapped[date | None] = mapped_column(Date, index=True)

    track: Mapped[Track | None] = mapped_column(Enum(Track, name="vacancy_track"))
    feedback: Mapped[str | None] = mapped_column(Text)   # что сказали после созвона/собеса

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    company: Mapped["Company"] = relationship(back_populates="vacancies")
    events: Mapped[list["Event"]] = relationship(
        back_populates="vacancy", cascade="all, delete-orphan", order_by="Event.happened_at.desc()"
    )


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    vacancy_id: Mapped[int] = mapped_column(ForeignKey("vacancies.id", ondelete="CASCADE"), index=True)
    type: Mapped[EventType] = mapped_column(Enum(EventType, name="event_type"), default=EventType.note)
    title: Mapped[str] = mapped_column(String(300))
    details: Mapped[str | None] = mapped_column(Text)
    happened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    calendar_event_id: Mapped[str | None] = mapped_column(String(200))  # связь с Google Calendar

    vacancy: Mapped["Vacancy"] = relationship(back_populates="events")


class PitchBlock(Base):
    """«Кирпич» рассказа о себе: якорь, место работы или блок про движение вперёд.

    Учится не текст, а блоки - тогда рассказ не рассыпается, если перебили или попросили короче.
    """

    __tablename__ = "pitch_blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(50), unique=True)   # anchor, mgt, alfa, trinfico, future
    position: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(200))
    period: Mapped[str | None] = mapped_column(String(100))

    core_line: Mapped[str] = mapped_column(Text)                # опорное предложение
    core_line_alt: Mapped[str | None] = mapped_column(Text)     # вариант под другой трек
    alt_for_track: Mapped[Track | None] = mapped_column(Enum(Track, name="alt_track"))

    in_short: Mapped[bool] = mapped_column(Boolean, default=True)   # входит ли в сборку на 40 секунд
    hint: Mapped[str | None] = mapped_column(Text)                  # как произносить

    addons: Mapped[list["PitchAddon"]] = relationship(
        back_populates="block", cascade="all, delete-orphan", order_by="PitchAddon.position"
    )


class PitchAddon(Base):
    """Добавка к кирпичу: берётся 1-2 из списка, а не весь список сразу."""

    __tablename__ = "pitch_addons"

    id: Mapped[int] = mapped_column(primary_key=True)
    block_id: Mapped[int] = mapped_column(ForeignKey("pitch_blocks.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    label: Mapped[str] = mapped_column(String(100))
    text: Mapped[str] = mapped_column(Text)
    tracks: Mapped[str | None] = mapped_column(String(100))   # где добавка сильна: "dev,ai"

    block: Mapped["PitchBlock"] = relationship(back_populates="addons")

    def fits(self, track: Track | None) -> bool:
        if track is None or not self.tracks:
            return False
        return track.value in [t.strip() for t in self.tracks.split(",")]


class TrackFocus(Base):
    """Акценты под тип вакансии: что усилить, что убрать."""

    __tablename__ = "track_focus"

    id: Mapped[int] = mapped_column(primary_key=True)
    track: Mapped[Track] = mapped_column(Enum(Track, name="focus_track"), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    emphasize: Mapped[str] = mapped_column(Text)
    drop: Mapped[str] = mapped_column(Text)


class PitchTip(Base):
    """Крючки, частые продолжения и то, чего избегать."""

    __tablename__ = "pitch_tips"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)   # hook | faq | avoid
    position: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str | None] = mapped_column(Text)


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str | None] = mapped_column(String(200))
    telegram: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)

    company: Mapped["Company"] = relationship(back_populates="contacts")
