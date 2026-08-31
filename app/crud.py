"""Операции с данными: всё обращение к БД собрано здесь."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app import models, schemas

# Статусы, означающие, что работодатель как-то отреагировал
RESPONDED = {
    models.Status.screening,
    models.Status.interview,
    models.Status.offer,
    models.Status.rejected,
}


def get_or_create_company(session: Session, name: str) -> models.Company:
    company = session.scalar(select(models.Company).where(models.Company.name == name))
    if company is None:
        company = models.Company(name=name)
        session.add(company)
        session.flush()
    return company


def list_vacancies(
    session: Session,
    status: models.Status | None = None,
    search: str | None = None,
) -> list[models.Vacancy]:
    stmt = select(models.Vacancy).options(selectinload(models.Vacancy.company))
    if status is not None:
        stmt = stmt.where(models.Vacancy.status == status)
    if search:
        pattern = f"%{search.lower()}%"
        stmt = stmt.join(models.Company).where(
            func.lower(models.Vacancy.title).like(pattern)
            | func.lower(models.Company.name).like(pattern)
        )
    stmt = stmt.order_by(models.Vacancy.priority, models.Vacancy.updated_at.desc())
    return list(session.scalars(stmt))


def get_vacancy(session: Session, vacancy_id: int) -> models.Vacancy | None:
    stmt = (
        select(models.Vacancy)
        .options(selectinload(models.Vacancy.company), selectinload(models.Vacancy.events))
        .where(models.Vacancy.id == vacancy_id)
    )
    return session.scalar(stmt)


def create_vacancy(session: Session, payload: schemas.VacancyCreate) -> models.Vacancy:
    company = get_or_create_company(session, payload.company_name)
    data = payload.model_dump(exclude={"company_name"})
    vacancy = models.Vacancy(company_id=company.id, **data)
    session.add(vacancy)
    session.commit()
    session.refresh(vacancy)
    return vacancy


def update_vacancy(
    session: Session, vacancy: models.Vacancy, payload: schemas.VacancyUpdate
) -> models.Vacancy:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(vacancy, field, value)
    session.commit()
    session.refresh(vacancy)
    return vacancy


def delete_vacancy(session: Session, vacancy: models.Vacancy) -> None:
    session.delete(vacancy)
    session.commit()


def add_event(
    session: Session, vacancy: models.Vacancy, payload: schemas.EventCreate
) -> models.Event:
    data = payload.model_dump()
    if data.get("happened_at") is None:
        data["happened_at"] = datetime.now(timezone.utc)
    event = models.Event(vacancy_id=vacancy.id, **data)
    session.add(event)

    # Событие двигает воронку: статус подтягивается автоматически
    moves = {
        models.EventType.applied: models.Status.applied,
        models.EventType.questionnaire: models.Status.screening,
        models.EventType.call: models.Status.screening,
        models.EventType.interview: models.Status.interview,
        models.EventType.test_task: models.Status.interview,
        models.EventType.offer: models.Status.offer,
        models.EventType.rejection: models.Status.rejected,
    }
    new_status = moves.get(event.type)
    if new_status is not None:
        vacancy.status = new_status
        if event.type == models.EventType.applied and vacancy.applied_at is None:
            vacancy.applied_at = date.today()

    session.commit()
    session.refresh(event)
    return event


LENGTH_LABEL = {
    models.PitchLength.short: "40 секунд - HR просит коротко",
    models.PitchLength.standard: "2 минуты - основной вариант",
    models.PitchLength.full: "4-5 минут - технарь просит подробно",
}

# Подсказки по ключевым словам вакансии, если трек не проставлен вручную
TRACK_HINTS = {
    models.Track.dev: ("c#", ".net", "backend", "бэкенд", "разработчик", "программист"),
    models.Track.ai: ("ai", "ии", "llm", "prompt", "нейросет", "автоматизац", "агент"),
    models.Track.support: ("поддержк", "сопровожден", "l2", "l3", "инженер", "эксплуатац", "данных"),
}


def guess_track(vacancy: models.Vacancy) -> models.Track | None:
    """Если трек не проставлен - угадываем по названию роли."""
    if vacancy.track is not None:
        return vacancy.track
    title = vacancy.title.lower()
    for track, words in TRACK_HINTS.items():
        if any(word in title for word in words):
            return track
    return None


AUDIENCE_LABEL = {
    models.Audience.hr: "HR-этап - слушают результат, масштаб и людей",
    models.Audience.tech: "техсобес - слушают, как именно устроено и что решал",
    models.Audience.both: "без деления по слушателю",
}


def vacancy_asks(vacancy: models.Vacancy | None) -> list[str]:
    """Что уточнить именно по этой вакансии - выводится из её же данных."""
    if vacancy is None:
        return []

    asks: list[str] = []
    if vacancy.salary_min is None and vacancy.salary_max is None:
        asks.append("Вилка не указана - спросить про неё, и лучше первым вопросом.")
    if vacancy.work_format is models.WorkFormat.unknown:
        asks.append("Формат работы неизвестен - уточнить офис, гибрид или удалёнка.")

    # Всё, что при разборе помечено как настораживающее, стоит проговорить вслух
    for line in (vacancy.match_note or "").splitlines():
        line = line.strip()
        if line.startswith("⚠️") or "СВЕРИТЬ" in line or "решить" in line.lower():
            asks.append(line.lstrip("⚠️ ").strip())

    if vacancy.status is models.Status.screening:
        asks.append("Уточнить, сколько всего этапов впереди и что на каждом проверяют.")
    return asks


def build_pitch(
    session: Session,
    length: models.PitchLength = models.PitchLength.standard,
    vacancy: models.Vacancy | None = None,
    track: models.Track | None = None,
    audience: models.Audience = models.Audience.both,
) -> schemas.Pitch:
    """Собирает рассказ о себе под длительность, тип вакансии и слушателя.

    Три измерения: сколько времени есть, какая это вакансия и кто напротив.
    Короткая версия - только опорные предложения без Альфа-Банка. В длинных
    первыми идут добавки, подходящие треку и слушателю.
    """
    if track is None and vacancy is not None:
        track = guess_track(vacancy)

    limit = models.ADDONS_PER_LENGTH[length]
    blocks_stmt = (
        select(models.PitchBlock)
        .options(selectinload(models.PitchBlock.addons))
        .order_by(models.PitchBlock.position)
    )

    blocks: list[schemas.PitchBlockRead] = []
    highlights: list[str] = []

    for block in session.scalars(blocks_stmt):
        if length is models.PitchLength.short and not block.in_short:
            continue

        core = block.core_line
        if block.core_line_alt and track is not None and block.alt_for_track is track:
            core = block.core_line_alt

        chosen: list[models.PitchAddon] = []
        if limit:
            suited = [a for a in block.addons if a.for_audience(audience)]
            # Первыми - те, что и под трек, и под слушателя
            fitting = [a for a in suited if a.fits(track)]
            rest = [a for a in suited if not a.fits(track)]
            chosen = (fitting + rest)[:limit]
            highlights.extend(f"{block.title}: {a.label}" for a in fitting[:limit])

        blocks.append(
            schemas.PitchBlockRead(
                key=block.key,
                title=block.title,
                period=block.period,
                core_line=core,
                hint=block.hint,
                reason_public=block.reason_public,
                reason_real=block.reason_real,
                addons=[
                    schemas.AddonRead(
                        label=a.label, text=a.text, audience=a.audience, fits_track=a.fits(track)
                    )
                    for a in chosen
                ],
            )
        )

    focus = None
    if track is not None:
        focus_row = session.scalar(select(models.TrackFocus).where(models.TrackFocus.track == track))
        if focus_row is not None:
            focus = schemas.FocusRead.model_validate(focus_row)

    tips = list(session.scalars(select(models.PitchTip).order_by(models.PitchTip.position)))
    pick = lambda kind: [schemas.TipRead.model_validate(t) for t in tips if t.kind == kind]

    # Вопросы для того этапа, на котором сейчас находимся
    q_stmt = select(models.StageQuestion).order_by(models.StageQuestion.position)
    if audience is not models.Audience.both:
        q_stmt = q_stmt.where(
            models.StageQuestion.audience.in_([audience, models.Audience.both])
        )
    questions = list(session.scalars(q_stmt))
    ask = lambda kind: [
        schemas.QuestionRead.model_validate(q) for q in questions if q.kind == kind
    ]

    return schemas.Pitch(
        length=length,
        length_label=LENGTH_LABEL[length],
        audience=audience,
        audience_label=AUDIENCE_LABEL[audience],
        track=track,
        vacancy_id=vacancy.id if vacancy else None,
        vacancy_title=vacancy.title if vacancy else None,
        company=vacancy.company.name if vacancy else None,
        blocks=blocks,
        focus=focus,
        highlights=highlights,
        hooks=pick("hook"),
        faq=pick("faq"),
        avoid=pick("avoid"),
        probe=ask("probe"),
        interest=ask("interest"),
        vacancy_asks=vacancy_asks(vacancy),
    )


def get_stats(session: Session, stale_days: int = 7, horizon_days: int = 7) -> schemas.Stats:
    vacancies = list(
        session.scalars(select(models.Vacancy).options(selectinload(models.Vacancy.company)))
    )

    by_status: dict[str, int] = {}
    for vacancy in vacancies:
        by_status[vacancy.status.value] = by_status.get(vacancy.status.value, 0) + 1

    applied = [v for v in vacancies if v.applied_at is not None]
    responded = [v for v in applied if v.status in RESPONDED]
    reply_rate = round(len(responded) / len(applied) * 100, 1) if applied else 0.0

    threshold = date.today() - timedelta(days=stale_days)
    stale = [
        v
        for v in applied
        if v.status == models.Status.applied and v.applied_at is not None and v.applied_at <= threshold
    ]

    horizon = date.today() + timedelta(days=horizon_days)
    upcoming = sorted(
        (v for v in vacancies if v.next_action_at is not None and v.next_action_at <= horizon),
        key=lambda v: v.next_action_at or date.max,
    )

    return schemas.Stats(
        total=len(vacancies),
        by_status=by_status,
        applied_count=len(applied),
        reply_rate=reply_rate,
        stale=[schemas.VacancyRead.model_validate(v) for v in stale],
        upcoming=[schemas.VacancyRead.model_validate(v) for v in upcoming],
    )
