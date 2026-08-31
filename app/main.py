"""Точка входа: REST API трекера откликов."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status as http_status
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.database import get_session, init_db

app = FastAPI(
    title="Трекер откликов",
    description="Учёт вакансий, откликов и событий по ним",
    version="0.1.0",
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@app.get("/", response_class=HTMLResponse, tags=["интерфейс"], include_in_schema=False)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/health", tags=["служебное"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/vacancies", response_model=list[schemas.VacancyRead], tags=["вакансии"])
def list_vacancies(
    status_filter: models.Status | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, min_length=2),
    session: Session = Depends(get_session),
):
    return crud.list_vacancies(session, status=status_filter, search=search)


@app.post(
    "/api/vacancies",
    response_model=schemas.VacancyRead,
    status_code=http_status.HTTP_201_CREATED,
    tags=["вакансии"],
)
def create_vacancy(payload: schemas.VacancyCreate, session: Session = Depends(get_session)):
    return crud.create_vacancy(session, payload)


@app.get("/api/vacancies/{vacancy_id}", response_model=schemas.VacancyDetail, tags=["вакансии"])
def get_vacancy(vacancy_id: int, session: Session = Depends(get_session)):
    vacancy = crud.get_vacancy(session, vacancy_id)
    if vacancy is None:
        raise HTTPException(status_code=404, detail="Вакансия не найдена")
    return vacancy


@app.patch("/api/vacancies/{vacancy_id}", response_model=schemas.VacancyRead, tags=["вакансии"])
def update_vacancy(
    vacancy_id: int, payload: schemas.VacancyUpdate, session: Session = Depends(get_session)
):
    vacancy = crud.get_vacancy(session, vacancy_id)
    if vacancy is None:
        raise HTTPException(status_code=404, detail="Вакансия не найдена")
    return crud.update_vacancy(session, vacancy, payload)


@app.delete(
    "/api/vacancies/{vacancy_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    tags=["вакансии"],
)
def delete_vacancy(vacancy_id: int, session: Session = Depends(get_session)):
    vacancy = crud.get_vacancy(session, vacancy_id)
    if vacancy is None:
        raise HTTPException(status_code=404, detail="Вакансия не найдена")
    crud.delete_vacancy(session, vacancy)


@app.post(
    "/api/vacancies/{vacancy_id}/events",
    response_model=schemas.EventRead,
    status_code=http_status.HTTP_201_CREATED,
    tags=["события"],
)
def add_event(
    vacancy_id: int, payload: schemas.EventCreate, session: Session = Depends(get_session)
):
    vacancy = crud.get_vacancy(session, vacancy_id)
    if vacancy is None:
        raise HTTPException(status_code=404, detail="Вакансия не найдена")
    return crud.add_event(session, vacancy, payload)


@app.get("/api/stats", response_model=schemas.Stats, tags=["аналитика"])
def get_stats(session: Session = Depends(get_session)):
    return crud.get_stats(session)


@app.get("/api/pitch", response_model=schemas.Pitch, tags=["рассказ о себе"])
def get_pitch(
    length: models.PitchLength = Query(default=models.PitchLength.standard),
    track: models.Track | None = Query(default=None),
    session: Session = Depends(get_session),
):
    """Рассказ о себе, собранный под длительность и тип вакансии."""
    return crud.build_pitch(session, length=length, track=track)


@app.get("/api/vacancies/{vacancy_id}/pitch", response_model=schemas.Pitch, tags=["рассказ о себе"])
def get_vacancy_pitch(
    vacancy_id: int,
    length: models.PitchLength = Query(default=models.PitchLength.standard),
    session: Session = Depends(get_session),
):
    """То же, но с акцентами под конкретную вакансию."""
    vacancy = crud.get_vacancy(session, vacancy_id)
    if vacancy is None:
        raise HTTPException(status_code=404, detail="Вакансия не найдена")
    return crud.build_pitch(session, length=length, vacancy=vacancy)


def _ics_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


@app.get("/calendar.ics", tags=["интеграции"])
def calendar_feed(session: Session = Depends(get_session)) -> Response:
    """Календарная лента: ближайшие действия по вакансиям и назначенные созвоны/интервью.

    Импортируется в Google Calendar (Настройки -> Импорт) или любым клиентом с поддержкой iCalendar.
    """
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//vacancy-tracker//RU",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:Трекер откликов",
    ]

    # Ближайшие действия: событие на весь день в дату next_action_at
    vacancies = session.scalars(
        select(models.Vacancy).where(models.Vacancy.next_action_at.is_not(None))
    ).all()
    for v in vacancies:
        day = v.next_action_at.strftime("%Y%m%d")
        day_end = (v.next_action_at + timedelta(days=1)).strftime("%Y%m%d")
        summary = f"{v.company.name}: {v.next_action or 'следующее действие'}"
        lines += [
            "BEGIN:VEVENT",
            f"UID:vacancy-{v.id}-action@vacancy-tracker",
            f"DTSTART;VALUE=DATE:{day}",
            f"DTEND;VALUE=DATE:{day_end}",
            f"SUMMARY:{_ics_escape(summary)}",
            f"DESCRIPTION:{_ics_escape(v.title)}",
            "END:VEVENT",
        ]

    # Назначенные созвоны, интервью и тестовые с датой в будущем
    scheduled_types = (
        models.EventType.call,
        models.EventType.interview,
        models.EventType.test_task,
    )
    events = session.scalars(
        select(models.Event).where(
            models.Event.type.in_(scheduled_types),
            models.Event.happened_at >= date.today(),
        )
    ).all()
    for e in events:
        stamp = e.happened_at.strftime("%Y%m%dT%H%M%S")
        end = (e.happened_at + timedelta(hours=1)).strftime("%Y%m%dT%H%M%S")
        summary = f"{e.vacancy.company.name}: {e.title}"
        lines += [
            "BEGIN:VEVENT",
            f"UID:event-{e.id}@vacancy-tracker",
            f"DTSTART:{stamp}",
            f"DTEND:{end}",
            f"SUMMARY:{_ics_escape(summary)}",
            f"DESCRIPTION:{_ics_escape(e.details or e.vacancy.title)}",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    return Response(
        content="\r\n".join(lines) + "\r\n",
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="vacancy-tracker.ics"'},
    )
