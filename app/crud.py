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
