"""Точка входа: REST API трекера откликов."""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status as http_status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
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
